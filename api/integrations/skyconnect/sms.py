"""
SkyConnect SMS over HTTP.

The transport for one thing only: telling somebody their telebirr
subscription is active. The short-code and TIMWE flows keep SMPP -- see
`api/services/sms/timwe_smpp.py` -- because changing how those notify would
change a working production path for no reason.

This module speaks HTTP and nothing else. It does not decide who to message,
does not retry, and does not record anything: those belong to the dispatch
layer (`api/services/sms/dispatch.py`), which already owns idempotency,
delivery state and retry for every provider. Adding a transport should not
mean reimplementing any of that, which is why the gateway contract exists.

Secrets
-------
The API key is read from configuration at call time and goes into the
Authorization header. It is never logged, never put in an exception message,
and never returned: the failure paths below quote the status code and the
provider's own error text, both of which are safe, and say nothing about the
credential used.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

#: The provider's own timeout. Long enough for a slow gateway, short enough
#: that a Celery worker is not parked on one message.
TIMEOUT_SECONDS = 15


class SkyConnectError(Exception):
    """The provider refused, failed, or could not be reached."""

    def __init__(self, message, *, retryable):
        super().__init__(message)
        #: Whether trying the same message again could plausibly work. A
        #: timeout or a 5xx can; a malformed number cannot.
        self.retryable = retryable


class SkyConnectNotConfigured(SkyConnectError):
    """No URL or key. A deployment problem, not a delivery problem."""

    def __init__(self, message):
        super().__init__(message, retryable=False)


def _config():
    url = getattr(settings, 'SKYCONNECT_SMS_API_URL', '') or ''
    key = getattr(settings, 'SKYCONNECT_SMS_API_KEY', '') or ''
    sender = getattr(settings, 'SKYCONNECT_SMS_SENDER_ID', '') or ''
    if not url or not key:
        # Names the setting, never the value.
        raise SkyConnectNotConfigured(
            'SkyConnect SMS is not configured: set SKYCONNECT_SMS_API_URL and '
            'SKYCONNECT_SMS_API_KEY.'
        )
    return url, key, sender


def to_msisdn(destination):
    """The provider's format: +2519XXXXXXXX.

    Everything else in this system stores and looks up numbers as
    251XXXXXXXXX (see common/validators/phone.py), so the leading plus is
    added here rather than changing what the rest of the app considers a
    phone number.
    """
    digits = ''.join(ch for ch in str(destination or '') if ch.isdigit())
    if not digits:
        return ''
    return f'+{digits}'


def send_sms(*, destination, text):
    """Send one message. Returns the provider's message id, or ''.

    Raises SkyConnectError for anything that did not result in the provider
    accepting the message. The caller decides what that means for the
    subscription -- which is nothing: a subscription that has been paid for
    is not undone because a notification failed.
    """
    url, key, sender = _config()
    to = to_msisdn(destination)
    if not to:
        raise SkyConnectError(f'Not a usable destination: {destination!r}', retryable=False)

    payload = {'to': to, 'body': text, 'senderId': sender}
    headers = {
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
    }

    masked = f'{to[:6]}****{to[-3:]}' if len(to) > 9 else '****'
    logger.info('SKYCONNECT_SEND_STARTED to=%s len=%s', masked, len(text))

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
    except requests.Timeout as exc:
        # Ambiguous: the provider may already hold the message. Reported as
        # retryable because the dispatch layer, not this module, decides how
        # to weigh a possible duplicate against a possible loss.
        logger.warning('SKYCONNECT_TIMEOUT to=%s after=%ss', masked, TIMEOUT_SECONDS)
        raise SkyConnectError('SkyConnect timed out', retryable=True) from exc
    except requests.RequestException as exc:
        # The exception text can carry the request URL but never the header.
        logger.warning('SKYCONNECT_UNREACHABLE to=%s error=%s', masked, type(exc).__name__)
        raise SkyConnectError('Could not reach SkyConnect', retryable=True) from exc

    if response.status_code >= 500:
        logger.warning('SKYCONNECT_SERVER_ERROR to=%s http=%s', masked, response.status_code)
        raise SkyConnectError(f'SkyConnect returned HTTP {response.status_code}', retryable=True)

    if response.status_code >= 400:
        # 4xx is our fault -- a bad number, a rejected sender id, an expired
        # key. Retrying sends the same request to the same answer.
        detail = (response.text or '')[:200]
        logger.warning(
            'SKYCONNECT_REJECTED to=%s http=%s detail=%s', masked, response.status_code, detail
        )
        raise SkyConnectError(
            f'SkyConnect rejected the message (HTTP {response.status_code})', retryable=False
        )

    message_id = ''
    try:
        body = response.json()
        if isinstance(body, dict):
            message_id = str(
                body.get('messageId') or body.get('id') or body.get('message_id') or ''
            )
    except ValueError:
        # Accepted with a body we do not recognise. The message is away; not
        # being able to name it only costs us correlation later.
        logger.info('SKYCONNECT_ACCEPTED_UNPARSED to=%s http=%s', masked, response.status_code)

    logger.info(
        'SKYCONNECT_SENT to=%s http=%s message_id=%s', masked, response.status_code, message_id
    )
    return message_id


def health():
    """Operational state, free of credentials."""
    url = getattr(settings, 'SKYCONNECT_SMS_API_URL', '') or ''
    return {
        'provider': 'skyconnect',
        'configured': bool(url and getattr(settings, 'SKYCONNECT_SMS_API_KEY', '')),
        'endpoint': url,
        'sender_id': getattr(settings, 'SKYCONNECT_SMS_SENDER_ID', ''),
    }
