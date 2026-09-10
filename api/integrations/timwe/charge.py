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

Success is signalled by an empty ``chargeAmountResponse`` element (guide
p.22). Every failure carries an SVC/POL code, which errors.py splits into
retryable MA-side faults and permanent ones.

Not the SMPP link
-----------------
This is a separate API on a separate endpoint with its own credentials. The
SMPP gateway (TIMWE_SMPP_HOST/PORT) carries SMS; it is not where chargeAmount
is sent. The only SMPP settings read here are that host and port, and only to
refuse a TIMWE_CHARGE_URL pointed at them. TIMWE_CHARGE_URL must be supplied
by TIMWE explicitly -- the guide's ``http://IP:Port/...`` template is refused.

The master switch
-----------------
While TIMWE_CHARGING_ENABLED is false, :meth:`TimweChargeService.execute`
refuses before building a request. Every charge in the application goes through
it, so the switch holds whoever the caller is.

What this module is, and is not
-------------------------------
It speaks the protocol and classifies the answer. It does not record
anything, decide whether a charge should happen, or guard against a repeat --
those are the business layer's job, in api/services/timwe_charging.py, which
is the only thing that should call :meth:`TimweChargeService.execute`.

Built with an f-string template and parsed with ElementTree, matching
api/services/crm_service.py and api/integrations/telebirr/direct_debit.py
rather than introducing a second SOAP idiom into the codebase.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

import requests
import urllib3.exceptions
from django.conf import settings
from django.utils import timezone

from api.integrations.timwe.errors import (
    CHARGE_AMOUNT_ERRORS,
    CHARGE_PERMANENT,
    CHARGE_RETRYABLE,
    TimweAmountError,
    TimweChargingDisabled,
    TimweConfigurationError,
    TimweError,
)
from common.validators.phone import normalize_ethiopian_phone

logger = logging.getLogger(__name__)

#: Pieces of the guide's ``http://IP:Port/AmountChargingService/...`` template.
#: A TIMWE_CHARGE_URL containing one was copied from the documentation, not
#: supplied by TIMWE.
PLACEHOLDER_MARKERS = ('ip:port', '<ip>', '{ip}', '<port>', '{port}')

#: Guide p.17: "The MA sends a response within 60 seconds by default." Our
#: read deadline defaults to that, because giving up earlier would turn a slow
#: but successful charge into an ambiguous one.
DEFAULT_TIMEOUT = 60

#: A connection that cannot even be opened in this long will not be. Kept far
#: below the read timeout: failing to connect is safe to report quickly,
#: because nothing was sent.
CONNECT_TIMEOUT = 10

#: Guide p.21: xsd:decimal, length 4, "does not support the decimal point".
MAX_AMOUNT_DIGITS = 4

#: Guide p.21: referenceCode, xsd:string, length 30.
MAX_REFERENCE_CODE_LENGTH = 30

#: Guide p.21: ChargingInformation.description, length 255, mandatory.
MAX_DESCRIPTION_LENGTH = 255

#: Guide p.21: currency is an ISO 4217 code, length 3.
CURRENCY_PATTERN = re.compile(r'^[A-Z]{3}$')

#: Guide pp.22-24: every chargeAmount error code is SVC or POL plus four
#: digits. A faultcode that does not look like this -- ``soapenv:Server``, say
#: -- is SOAP's own classification, not the MA's error code.
MA_ERROR_CODE = re.compile(r'^(SVC|POL)\d{4}$')


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

#: The MA accepted the charge.
OUTCOME_SUCCESS = 'success'
#: The MA answered with a Fault. Definite: the subscriber was not charged.
OUTCOME_REJECTED = 'rejected'
#: The request never reached the MA -- refused, DNS, connect timeout.
#: Definite: nothing was sent, so nothing was charged.
OUTCOME_UNREACHABLE = 'unreachable'
#: Sent, but no answer inside the read deadline. AMBIGUOUS: the MA may have
#: charged and the reply been lost.
OUTCOME_TIMEOUT = 'timeout'
#: An answer we cannot interpret, or a connection that broke after sending.
#: AMBIGUOUS for the same reason.
OUTCOME_UNKNOWN = 'unknown'

AMBIGUOUS_OUTCOMES = frozenset({OUTCOME_TIMEOUT, OUTCOME_UNKNOWN})


@dataclass(frozen=True)
class ChargeOutcome:
    """What happened to one chargeAmount call.

    The distinction that matters is between an outcome that *proves* the
    subscriber was not charged and one that merely failed to prove they were.
    A network timeout is the second kind -- treating it as the first is how a
    retry charges someone twice.
    """

    outcome: str
    error_code: str | None = None
    message: str = ''
    http_status: int | None = None
    duration_ms: int | None = None

    @property
    def success(self) -> bool:
        return self.outcome == OUTCOME_SUCCESS

    @property
    def is_ambiguous(self) -> bool:
        """The subscriber may or may not have been charged."""
        return self.outcome in AMBIGUOUS_OUTCOMES

    @property
    def definitely_not_charged(self) -> bool:
        return self.outcome in (OUTCOME_REJECTED, OUTCOME_UNREACHABLE)


class TimweChargeService:
    """chargeAmount over Parlay X 3.1."""

    # -- configuration -----------------------------------------------------

    @classmethod
    def get_endpoint(cls) -> str:
        return getattr(settings, 'TIMWE_CHARGE_URL', '') or ''

    @classmethod
    def get_sp_id(cls) -> str:
        return getattr(settings, 'TIMWE_SP_ID', '') or ''

    @classmethod
    def get_sp_account_password(cls) -> str:
        return getattr(settings, 'TIMWE_SP_PASSWORD', '') or ''

    @classmethod
    def get_service_id(cls) -> str:
        return getattr(settings, 'TIMWE_SERVICE_ID', '') or ''

    @classmethod
    def get_currency(cls) -> str:
        return getattr(settings, 'TIMWE_CURRENCY', '') or ''

    @classmethod
    def get_timeout(cls) -> int:
        """The read deadline, in seconds.

        Refuses a value that is not a positive integer rather than letting
        ``int('abc')`` escape as a bare ValueError, or silently using zero --
        which would time out every charge before the MA could answer.
        """
        raw = getattr(settings, 'TIMWE_CHARGE_TIMEOUT', DEFAULT_TIMEOUT)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise TimweConfigurationError(
                'TIMWE_CHARGE_TIMEOUT must be a positive whole number of seconds.'
            ) from exc
        if value <= 0:
            raise TimweConfigurationError(
                'TIMWE_CHARGE_TIMEOUT must be a positive whole number of seconds.'
            )
        return value

    @classmethod
    def missing_configuration(cls) -> list[str]:
        """Names of the settings chargeAmount cannot be built without.

        Names only -- never values. This ends up in exceptions and logs.
        """
        return [
            name
            for name, value in (
                ('TIMWE_CHARGE_URL', cls.get_endpoint()),
                ('TIMWE_SP_ID', cls.get_sp_id()),
                ('TIMWE_SP_PASSWORD', cls.get_sp_account_password()),
                ('TIMWE_SERVICE_ID', cls.get_service_id()),
                ('TIMWE_CURRENCY', cls.get_currency()),
            )
            if not value
        ]

    @classmethod
    def is_configured(cls) -> bool:
        """True when every value chargeAmount cannot be built without is set."""
        return not cls.missing_configuration()

    @classmethod
    def charging_enabled(cls) -> bool:
        """The master switch. While it is off nothing is sent, whoever asks."""
        return bool(getattr(settings, 'TIMWE_CHARGING_ENABLED', False))

    @classmethod
    def endpoint_problem(cls) -> str:
        """Why TIMWE_CHARGE_URL cannot be the AmountCharging endpoint, or ''.

        Refuses the two mistakes this integration has already come close to:
        the guide's ``http://IP:Port/...`` template configured literally, and
        the SMPP gateway's host and port reused for charging. The same host on
        a different port is allowed -- TIMWE may well serve both from one box.
        An unset URL is not a problem here; missing_configuration reports it.
        """
        url = cls.get_endpoint().strip()
        if not url:
            return ''
        if any(marker in url.lower() for marker in PLACEHOLDER_MARKERS):
            return (
                'TIMWE_CHARGE_URL is still the documentation placeholder '
                '(http://IP:Port/...). TIMWE must supply the real address.'
            )
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            return 'TIMWE_CHARGE_URL is not a valid URL.'
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            return 'TIMWE_CHARGE_URL must be an http(s) URL with a host.'

        effective_port = port or (443 if parts.scheme == 'https' else 80)
        smpp_host = (getattr(settings, 'TIMWE_SMPP_HOST', '') or '').strip().lower()
        try:
            smpp_port = int(getattr(settings, 'TIMWE_SMPP_PORT', 0) or 0)
        except (TypeError, ValueError):
            smpp_port = 0
        if smpp_host and parts.hostname.lower() == smpp_host and effective_port == smpp_port:
            return (
                'TIMWE_CHARGE_URL points at the SMPP gateway (TIMWE_SMPP_HOST:TIMWE_SMPP_PORT). '
                'chargeAmount is a separate endpoint that TIMWE must supply.'
            )
        return ''

    @classmethod
    def ensure_configured(cls) -> None:
        missing = cls.missing_configuration()
        if missing:
            raise TimweConfigurationError(
                f'TIMWE charging is not configured: {", ".join(missing)} unset. '
                'TIMWE_CHARGE_URL and the charging credentials must be supplied by '
                'TIMWE -- they are not the SMPP settings.'
            )
        problem = cls.endpoint_problem()
        if problem:
            raise TimweConfigurationError(problem)
        # Also validates the timeout, so a bad value fails here rather than
        # on the first real charge.
        cls.get_timeout()

    # -- authentication ----------------------------------------------------

    @classmethod
    def build_timestamp(cls) -> str:
        """UTC ``yyyyMMddHHmmss`` (guide p.20)."""
        return timezone.now().astimezone(UTC).strftime('%Y%m%d%H%M%S')

    @classmethod
    def build_sp_password(cls, timestamp: str) -> str:
        """
        ``MD5(spId + Password + timeStamp)`` (guide p.20).

        ``Password`` is the account password as supplied, hashed exactly once
        here. MD5 is the MA's choice, not ours: it is a message authenticator
        rather than a password hash, and the input contains a per-request
        timestamp. That is also why the digest must never be logged or reused.
        """
        raw = f'{cls.get_sp_id()}{cls.get_sp_account_password()}{timestamp}'
        return hashlib.md5(raw.encode('utf-8')).hexdigest()  # noqa: S324

    # -- field validation --------------------------------------------------

    @classmethod
    def format_amount(cls, amount: Decimal | int | str) -> str:
        """
        Render an amount for the wire, or refuse.

        The MA has no decimal point and four characters of room, so anything
        with a fractional part is unrepresentable. Rounding it silently would
        either under-bill us or over-bill the subscriber, so this raises
        instead and lets the caller decide.

        Zero is refused too: the guide treats a blank amount as SVC0002, and a
        charge of nothing is a bug in the caller rather than a transaction.
        """
        if isinstance(amount, bool) or isinstance(amount, float):
            # bool is an int subclass, and float cannot hold money exactly.
            # Both are refused before Decimal gets a chance to accept them.
            raise TimweAmountError(
                'Amount must be an int, Decimal or numeric string -- never a float.'
            )
        try:
            value = Decimal(str(amount).strip())
        except (InvalidOperation, ValueError) as exc:
            raise TimweAmountError(f'Amount {amount!r} is not a number.') from exc
        if not value.is_finite():
            raise TimweAmountError(f'Amount {amount!r} is not a finite number.')
        if value != value.to_integral_value():
            raise TimweAmountError(
                f'Amount {value} has a fractional part and the MA does not accept '
                'a decimal point (guide p.21). Charge an integer amount, or '
                'confirm a minor-unit convention with TIMWE.'
            )
        integral = int(value)
        if integral <= 0:
            raise TimweAmountError('Amount must be a positive whole number.')
        rendered = str(integral)
        if len(rendered) > MAX_AMOUNT_DIGITS:
            raise TimweAmountError(
                f'Amount {rendered} exceeds the {MAX_AMOUNT_DIGITS}-character '
                'limit the MA allows (guide p.21).'
            )
        return rendered

    @classmethod
    def normalize_msisdn(cls, msisdn: str) -> str:
        """The subscriber as ``251XXXXXXXXX``, or a refusal.

        The guide requires the country code in both the header (OA/FA, p.20)
        and the body (endUserIdentifier, p.21). This uses the same normaliser
        as login and SMS, so ``0912...``, ``+251912...`` and ``251912...`` all
        name one account -- and a local-format number can never reach the MA
        without its country code, which is what the previous digits-only
        stripping allowed.
        """
        normalized = normalize_ethiopian_phone(msisdn)
        if not normalized:
            raise TimweError('The MSISDN is not a valid Ethiopian mobile number.')
        return normalized

    @classmethod
    def format_end_user_identifier(cls, msisdn: str) -> str:
        """``tel:`` + MSISDN including country code (guide p.21)."""
        return f'tel:{cls.normalize_msisdn(msisdn)}'

    @classmethod
    def validate_description(cls, description: str) -> str:
        """Mandatory, and at most 255 characters (guide p.21)."""
        text = (description or '').strip()
        if not text:
            raise TimweError('A charge description is required (guide p.21).')
        if len(text) > MAX_DESCRIPTION_LENGTH:
            raise TimweError(
                f'Charge description exceeds {MAX_DESCRIPTION_LENGTH} characters ' '(guide p.21).'
            )
        return text

    @classmethod
    def validate_currency(cls) -> str:
        """The configured currency, checked as an ISO 4217 code (guide p.21)."""
        currency = cls.get_currency().strip().upper()
        if not CURRENCY_PATTERN.match(currency):
            raise TimweConfigurationError(
                'TIMWE_CURRENCY must be a three-letter ISO 4217 code, e.g. ETB.'
            )
        return currency

    @classmethod
    def validate_reference_code(cls, reference_code: str) -> str:
        if not reference_code or len(reference_code) > MAX_REFERENCE_CODE_LENGTH:
            raise TimweError(
                f'referenceCode must be 1-{MAX_REFERENCE_CODE_LENGTH} characters (guide p.21).'
            )
        return reference_code

    # -- request -----------------------------------------------------------

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

        Namespaces are exactly those of the guide's request example (p.19):
        the Huawei v2_1 common header and the Parlay X amount_charging v3_1
        local body. The response uses v2_1 (p.22); that asymmetry is the
        MA's, and parse_soap_response tolerates it rather than this changing
        the request to match.

        ``OA`` and ``FA`` are both the charged subscriber: the guide requires
        FA to equal OA (p.21), and FlipStar only ever charges the account that
        owns the purchase -- never a third-party gift payer.

        The one timestamp is used in the header *and* in the digest. Two
        separate clock reads can straddle a second boundary, and then the MA
        recomputes a different digest and rejects the charge as SVC0901.
        """
        cls.ensure_configured()
        cls.validate_reference_code(reference_code)
        text = cls.validate_description(description)
        currency = cls.validate_currency()
        rendered_amount = cls.format_amount(amount)
        subscriber = cls.normalize_msisdn(msisdn)

        timestamp = timestamp or cls.build_timestamp()
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
      <loc:endUserIdentifier>tel:{escape(subscriber)}</loc:endUserIdentifier>
      <loc:charge>
        <description>{escape(text)}</description>
        <currency>{escape(currency)}</currency>
        <amount>{rendered_amount}</amount>{code_element}
      </loc:charge>
      <loc:referenceCode>{escape(reference_code)}</loc:referenceCode>
    </loc:chargeAmount>
  </soapenv:Body>
</soapenv:Envelope>"""

    # -- response ----------------------------------------------------------

    @classmethod
    def _interpret(cls, response_text: str) -> tuple[str, str | None, str]:
        """Classify a reply body as success, rejected or unknown.

        Element lookups ignore namespaces on purpose: the guide's request
        uses the ``v3_1`` namespace while its response uses ``v2_1`` (pp.19,
        22), so matching on the full qualified name would reject valid replies.

        Success requires an actual ``chargeAmountResponse`` element. The
        previous rule -- any well-formed XML without a Fault -- would have
        read a proxy's XML error page as a successful charge.
        """
        if not response_text or not response_text.strip():
            return OUTCOME_UNKNOWN, None, 'Empty response from the MA.'

        try:
            root = ET.fromstring(response_text)  # noqa: S314
        except ET.ParseError as exc:
            return OUTCOME_UNKNOWN, None, f'Malformed SOAP response: {exc}'

        def localname(element) -> str:
            return element.tag.rsplit('}', 1)[-1]

        elements = list(root.iter())
        fault = next((el for el in elements if localname(el) == 'Fault'), None)

        if fault is None:
            if any(localname(el) == 'chargeAmountResponse' for el in elements):
                return OUTCOME_SUCCESS, None, 'Charged.'
            return (
                OUTCOME_UNKNOWN,
                None,
                'The MA replied without a Fault or a chargeAmountResponse.',
            )

        # Parlay X carries the MA's own code as <messageId> inside <detail>;
        # <faultcode> is usually SOAP's classification (soapenv:Server). Prefer
        # messageId, and accept a faultcode only when it is itself an SVC/POL
        # code -- otherwise "Server" would be stored as the error code.
        code = ''
        message = ''
        for child in fault.iter():
            name = localname(child)
            text = (child.text or '').strip()
            if not text:
                continue
            if name == 'messageId' and MA_ERROR_CODE.match(text):
                code = text
            elif name in ('faultcode', 'Value') and not code:
                candidate = text.rsplit(':', 1)[-1]
                if MA_ERROR_CODE.match(candidate):
                    code = candidate
            elif name in ('faultstring', 'Text', 'text', 'message') and not message:
                message = text

        code = code or None
        message = message or CHARGE_AMOUNT_ERRORS.get(code, 'The MA rejected the charge.')
        return OUTCOME_REJECTED, code, message

    @classmethod
    def parse_soap_response(cls, response_text: str) -> tuple[bool, str | None, str]:
        """Read a chargeAmount reply into ``(success, error_code, message)``."""
        outcome, code, message = cls._interpret(response_text)
        return outcome == OUTCOME_SUCCESS, code, message

    # -- transport ---------------------------------------------------------

    @staticmethod
    def _never_connected(exc: requests.exceptions.ConnectionError) -> bool:
        """True when the failure provably happened before anything was sent.

        requests reports refused connections, DNS failures and mid-stream
        resets all as ConnectionError. Only the first two are safe: they wrap
        urllib3's ConnectTimeoutError family (NewConnectionError and its
        NameResolutionError subclass). A reset after sending is a
        ProtocolError instead, and the MA may already have charged.
        """
        seen = set()
        pending = [exc]
        while pending:
            current = pending.pop()
            if current is None or id(current) in seen:
                continue
            seen.add(id(current))
            if isinstance(current, urllib3.exceptions.ConnectTimeoutError):
                return True
            pending.append(getattr(current, 'reason', None))
            pending.append(current.__cause__)
            pending.append(current.__context__)
            pending.extend(a for a in getattr(current, 'args', ()) if isinstance(a, BaseException))
        return False

    @classmethod
    def execute(
        cls,
        *,
        msisdn: str,
        amount: Decimal | int | str,
        description: str,
        reference_code: str,
        charge_code: str = '',
    ) -> ChargeOutcome:
        """Send one chargeAmount and classify what came back.

        Never raises for an MA-side or network failure -- those are outcomes.
        Configuration and input problems do raise, because they are our bugs
        and must not be mistaken for a subscriber who could not pay.

        Does not retry. Whether a charge may be attempted again depends on
        whether the last attempt was ambiguous, and that is a decision for the
        caller that owns the transaction record.

        Refuses with TimweChargingDisabled while TIMWE_CHARGING_ENABLED is
        off. This is the last line of the master switch: every chargeAmount in
        the application is sent from here.
        """
        if not cls.charging_enabled():
            raise TimweChargingDisabled(
                'TIMWE charging is switched off (TIMWE_CHARGING_ENABLED is false). '
                'Nothing was sent.'
            )
        envelope = cls.build_soap_request(
            msisdn=msisdn,
            amount=amount,
            description=description,
            reference_code=reference_code,
            charge_code=charge_code,
        )
        read_timeout = cls.get_timeout()

        started = time.monotonic()

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        try:
            response = requests.post(
                cls.get_endpoint(),
                data=envelope.encode('utf-8'),
                headers={'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': ''},
                timeout=(CONNECT_TIMEOUT, read_timeout),
            )
        except requests.exceptions.ConnectTimeout:
            # Must precede both handlers below: ConnectTimeout subclasses
            # ConnectionError *and* Timeout, and the Timeout branch would read
            # a connection that never opened as an ambiguous charge.
            return ChargeOutcome(
                OUTCOME_UNREACHABLE,
                message='Could not connect to the MA in time; nothing was sent.',
                duration_ms=elapsed(),
            )
        except requests.exceptions.ReadTimeout:
            return ChargeOutcome(
                OUTCOME_TIMEOUT,
                message=(
                    f'The MA did not answer within {read_timeout}s. The charge may '
                    'still have been applied.'
                ),
                duration_ms=elapsed(),
            )
        except requests.exceptions.ConnectionError as exc:
            if cls._never_connected(exc):
                return ChargeOutcome(
                    OUTCOME_UNREACHABLE,
                    message='Could not reach the MA; nothing was sent.',
                    duration_ms=elapsed(),
                )
            return ChargeOutcome(
                OUTCOME_UNKNOWN,
                message=(
                    'The connection to the MA broke after the request was sent. '
                    'The charge may still have been applied.'
                ),
                duration_ms=elapsed(),
            )
        except requests.exceptions.RequestException as exc:
            # Anything else requests can raise -- TooManyRedirects, an
            # invalid URL -- happens before a charge reaches the MA's handler.
            return ChargeOutcome(
                OUTCOME_UNREACHABLE,
                message=f'The request could not be sent: {type(exc).__name__}.',
                duration_ms=elapsed(),
            )

        outcome, code, message = cls._interpret(response.text)

        # A 4xx with no SOAP answer means the request never reached the charge
        # handler -- a wrong path, a refused method. Nothing was charged. A 5xx
        # with no Fault is different: the server may have got some way into
        # processing it, so it stays ambiguous.
        if outcome == OUTCOME_UNKNOWN and 400 <= response.status_code < 500:
            outcome = OUTCOME_REJECTED
            code = None
            message = f'The MA endpoint answered HTTP {response.status_code} without a SOAP reply.'
        elif outcome == OUTCOME_SUCCESS and response.status_code != 200:
            # A success body under an error status is not something to trust
            # with money.
            outcome = OUTCOME_UNKNOWN
            message = f'A success body arrived with HTTP {response.status_code}.'

        return ChargeOutcome(
            outcome,
            error_code=code,
            message=message,
            http_status=response.status_code,
            duration_ms=elapsed(),
        )

    # There used to be a ``charge()`` here: execute() reduced to a tuple, with
    # no record and no idempotency. Nothing called it, and a way to charge that
    # skips the transaction ledger is not one to leave lying around.

    @classmethod
    def is_retryable(cls, error_code: str | None) -> bool:
        return error_code in CHARGE_RETRYABLE

    @classmethod
    def is_permanent(cls, error_code: str | None) -> bool:
        return error_code in CHARGE_PERMANENT
