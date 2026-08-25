"""
TIMWE Master Aggregator chargeAmount client (outbound).

We are the client here: FlipStar calls the MA to deduct a fee from a
subscriber's account. Parlay X 3.1 over SOAP, per the integration guide
pp.17-24.

    POST http://IP:Port/AmountChargingService/services/AmountCharging

Authentication is a per-request MD5 digest rather than a static secret::

    spPassword = MD5(spId + Password + timeStamp)

``timeStamp`` is UTC ``yyyyMMddHHmmss`` and is sent alongside the digest so
the MA can recompute it. The account password itself never crosses the wire.

Success is signalled by the *absence* of a SOAP Fault -- a successful
chargeAmountResponse is an empty element (guide p.22). Every failure carries
an SVC/POL code, which errors.py splits into retryable MA-side faults and
permanent ones.

Built with an f-string template and parsed with ElementTree, matching
api/services/crm_service.py and api/integrations/telebirr/direct_debit.py
rather than introducing a second SOAP idiom into the codebase.
"""

from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import UTC
from decimal import Decimal
from xml.sax.saxutils import escape

import requests
from django.conf import settings
from django.utils import timezone

from api.integrations.timwe.errors import (
    CHARGE_AMOUNT_ERRORS,
    CHARGE_PERMANENT,
    CHARGE_RETRYABLE,
    CHARGE_TIMEOUT,
    TimweAmountError,
    TimweConfigurationError,
    TimweError,
)

logger = logging.getLogger(__name__)

#: Guide p.19. The MA answers within 60 seconds by default, so anything above
#: that is the network failing rather than the MA thinking.
DEFAULT_TIMEOUT = 60

#: Guide p.21: xsd:decimal, length 4, "does not support the decimal point".
MAX_AMOUNT_DIGITS = 4

#: Guide p.21: referenceCode, xsd:string, length 30.
MAX_REFERENCE_CODE_LENGTH = 30


class TimweChargeService:
    """chargeAmount over Parlay X 3.1."""

    @classmethod
    def get_endpoint(cls) -> str:
        return getattr(settings, 'TIMWE_CHARGE_URL', '')

    @classmethod
    def get_sp_id(cls) -> str:
        return getattr(settings, 'TIMWE_SP_ID', '')

    @classmethod
    def get_sp_account_password(cls) -> str:
        return getattr(settings, 'TIMWE_SP_PASSWORD', '')

    @classmethod
    def get_service_id(cls) -> str:
        return getattr(settings, 'TIMWE_SERVICE_ID', '')

    @classmethod
    def get_currency(cls) -> str:
        return getattr(settings, 'TIMWE_CURRENCY', '')

    @classmethod
    def get_timeout(cls) -> int:
        return int(getattr(settings, 'TIMWE_CHARGE_TIMEOUT', DEFAULT_TIMEOUT))

    @classmethod
    def is_configured(cls) -> bool:
        """True when every value chargeAmount cannot be built without is set."""
        return all(
            (
                cls.get_endpoint(),
                cls.get_sp_id(),
                cls.get_sp_account_password(),
                cls.get_service_id(),
                cls.get_currency(),
            )
        )

    @classmethod
    def build_timestamp(cls) -> str:
        """UTC ``yyyyMMddHHmmss`` (guide p.20)."""
        return timezone.now().astimezone(UTC).strftime('%Y%m%d%H%M%S')

    @classmethod
    def build_sp_password(cls, timestamp: str) -> str:
        """
        ``MD5(spId + Password + timeStamp)`` (guide p.20).

        MD5 is the MA's choice, not ours. It is a message authenticator here
        rather than a password hash, and the input already contains a
        per-request timestamp, so the usual preimage concerns do not apply --
        but it is also why the digest must never be logged or reused.
        """
        raw = f'{cls.get_sp_id()}{cls.get_sp_account_password()}{timestamp}'
        return hashlib.md5(raw.encode('utf-8')).hexdigest()  # noqa: S324

    @classmethod
    def format_amount(cls, amount: Decimal | int | str) -> str:
        """
        Render an amount for the wire, or refuse.

        The MA has no decimal point and four characters of room, so anything
        with a fractional part is unrepresentable. Rounding it silently would
        either under-bill us or over-bill the subscriber, so this raises
        instead and lets the caller decide.
        """
        value = Decimal(str(amount))
        if value != value.to_integral_value():
            raise TimweAmountError(
                f'Amount {value} has a fractional part and the MA does not accept '
                'a decimal point (guide p.21). Charge an integer amount, or '
                'confirm a minor-unit convention with TIMWE.'
            )
        integral = int(value)
        if integral < 0:
            raise TimweAmountError('Amount must not be negative.')
        rendered = str(integral)
        if len(rendered) > MAX_AMOUNT_DIGITS:
            raise TimweAmountError(
                f'Amount {rendered} exceeds the {MAX_AMOUNT_DIGITS}-character '
                'limit the MA allows (guide p.21).'
            )
        return rendered

    @classmethod
    def format_end_user_identifier(cls, msisdn: str) -> str:
        """``tel:`` + MSISDN including country code (guide p.21)."""
        digits = str(msisdn).strip().lstrip('+')
        if not digits.isdigit():
            raise TimweError(f'MSISDN {msisdn!r} is not a bare numeric subscriber number.')
        return f'tel:{digits}'

    @classmethod
    def build_soap_request(
        cls,
        *,
        msisdn: str,
        amount: Decimal | int | str,
        description: str,
        reference_code: str,
        charge_code: str = '',
        timestamp: str | None = None,
    ) -> str:
        """
        Build a chargeAmountRequest envelope.

        ``OA`` and ``FA`` are both the charged subscriber: the guide requires
        FA to equal OA (p.21), and FlipStar only ever charges the account that
        owns the subscription -- never a third-party gift payer.
        """
        if not cls.is_configured():
            raise TimweConfigurationError(
                'TIMWE charging is not configured. Required: TIMWE_CHARGE_URL, '
                'TIMWE_SP_ID, TIMWE_SP_PASSWORD, TIMWE_SERVICE_ID, TIMWE_CURRENCY.'
            )
        if not reference_code or len(reference_code) > MAX_REFERENCE_CODE_LENGTH:
            raise TimweError(
                f'referenceCode must be 1-{MAX_REFERENCE_CODE_LENGTH} characters ' '(guide p.21).'
            )

        timestamp = timestamp or cls.build_timestamp()
        subscriber = ''.join(ch for ch in str(msisdn).strip() if ch.isdigit())
        code_element = f'\n            <code>{escape(charge_code)}</code>' if charge_code else ''

        return f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
xmlns:v2="http://www.huawei.com.cn/schema/common/v2_1"
xmlns:loc="http://www.csapi.org/schema/parlayx/payment/amount_charging/v3_1/local">
  <soapenv:Header>
    <v2:RequestSOAPHeader>
      <v2:spId>{escape(cls.get_sp_id())}</v2:spId>
      <v2:spPassword>{cls.build_sp_password(timestamp)}</v2:spPassword>
      <v2:serviceId>{escape(cls.get_service_id())}</v2:serviceId>
      <v2:timeStamp>{timestamp}</v2:timeStamp>
      <v2:OA>{escape(subscriber)}</v2:OA>
      <v2:FA>{escape(subscriber)}</v2:FA>
      <v2:token/>
    </v2:RequestSOAPHeader>
  </soapenv:Header>
  <soapenv:Body>
    <loc:chargeAmount>
      <loc:endUserIdentifier>{escape(cls.format_end_user_identifier(msisdn))}</loc:endUserIdentifier>
      <loc:charge>
        <description>{escape(description)}</description>
        <currency>{escape(cls.get_currency())}</currency>
        <amount>{cls.format_amount(amount)}</amount>{code_element}
      </loc:charge>
      <loc:referenceCode>{escape(reference_code)}</loc:referenceCode>
    </loc:chargeAmount>
  </soapenv:Body>
</soapenv:Envelope>"""

    @classmethod
    def parse_soap_response(cls, response_text: str) -> tuple[bool, str | None, str]:
        """
        Read a chargeAmount reply into ``(success, error_code, message)``.

        A success response is an empty ``chargeAmountResponse`` element, so
        success is the absence of a Fault rather than the presence of any
        particular value (guide p.22).

        Element lookups ignore namespaces on purpose: the guide's own request
        example uses the ``v3_1`` namespace while its response example uses
        ``v2_1`` (pp.19, 22), so matching on the full qualified name would
        reject valid replies.
        """
        if not response_text or not response_text.strip():
            return False, None, 'Empty response from the MA.'

        try:
            root = ET.fromstring(response_text)  # noqa: S314
        except ET.ParseError as exc:
            return False, None, f'Malformed SOAP response: {exc}'

        def localname(element) -> str:
            return element.tag.rsplit('}', 1)[-1]

        fault = next((el for el in root.iter() if localname(el) == 'Fault'), None)
        if fault is None:
            return True, None, 'Charged.'

        code = ''
        message = ''
        for child in fault.iter():
            name = localname(child)
            if name in ('faultcode', 'Value') and child.text and not code:
                code = child.text.strip().rsplit(':', 1)[-1]
            elif name in ('faultstring', 'Text', 'message') and child.text and not message:
                message = child.text.strip()

        code = code or None
        message = message or CHARGE_AMOUNT_ERRORS.get(code, 'The MA rejected the charge.')
        return False, code, message

    @classmethod
    def charge(
        cls,
        *,
        msisdn: str,
        amount: Decimal | int | str,
        description: str,
        reference_code: str,
        charge_code: str = '',
    ) -> tuple[bool, str | None, str]:
        """
        Deduct a fee, returning ``(success, error_code, message)``.

        Never raises for an MA-side failure -- a declined charge is an
        outcome, not an exception. Configuration and amount problems do raise,
        because those are our bugs and must not be mistaken for a subscriber
        who cannot pay.
        """
        envelope = cls.build_soap_request(
            msisdn=msisdn,
            amount=amount,
            description=description,
            reference_code=reference_code,
            charge_code=charge_code,
        )

        # The envelope carries the MSISDN and the MD5 digest, so it is never
        # logged. reference_code is ours and safe to correlate on.
        logger.info('TIMWE chargeAmount requested', extra={'reference_code': reference_code})

        try:
            response = requests.post(
                cls.get_endpoint(),
                data=envelope.encode('utf-8'),
                headers={
                    'Content-Type': 'text/xml; charset=utf-8',
                    'SOAPAction': '',
                },
                timeout=cls.get_timeout(),
            )
        except requests.exceptions.Timeout:
            logger.warning('TIMWE chargeAmount timed out', extra={'reference_code': reference_code})
            return False, CHARGE_TIMEOUT, 'The MA did not respond in time.'
        except requests.exceptions.RequestException as exc:
            logger.warning(
                'TIMWE chargeAmount transport failure',
                extra={'reference_code': reference_code, 'error': str(exc)},
            )
            return False, None, f'Could not reach the MA: {exc}'

        success, code, message = cls.parse_soap_response(response.text)
        logger.info(
            'TIMWE chargeAmount completed',
            extra={
                'reference_code': reference_code,
                'success': success,
                'error_code': code or '',
                'http_status': response.status_code,
            },
        )
        return success, code, message

    @classmethod
    def is_retryable(cls, error_code: str | None) -> bool:
        return error_code in CHARGE_RETRYABLE

    @classmethod
    def is_permanent(cls, error_code: str | None) -> bool:
        return error_code in CHARGE_PERMANENT
