"""
Which gateway delivers application SMS.

Selected by ``settings.SMS_PROVIDER``. There is no fallback and no default
that reaches a real network: an unrecognised value raises rather than quietly
picking one.

    timwe_smpp   the production transport -- the only one that sends
    console      logs instead of sending; local development only

OneVAS has been removed. Its HTTP gateway used to remain here as an explicit
rollback option; it is gone, so no setting can route an SMS -- an OTP
included -- through OneVAS again. ``SMS_PROVIDER=onevas_http`` now fails like
any other unknown value.
"""

from django.core.exceptions import ImproperlyConfigured

from api.services.sms.base import SmsGateway, SubmitResult

__all__ = ['SmsGateway', 'SubmitResult', 'UnknownSmsProvider', 'get_gateway', 'reset_gateway']


class UnknownSmsProvider(ImproperlyConfigured):
    """SMS_PROVIDER names a gateway that does not exist."""


def _build(name) -> SmsGateway:
    if name == 'timwe_smpp':
        from api.services.sms.timwe_smpp import TimweSmppGateway

        return TimweSmppGateway()
    if name == 'console':
        from api.services.sms.console import ConsoleGateway

        return ConsoleGateway()
    raise UnknownSmsProvider(
        f'SMS_PROVIDER={name!r} is not a known gateway. '
        "Expected 'timwe_smpp' (production) or 'console' (development). "
        'OneVAS has been removed.'
    )


def get_gateway() -> SmsGateway:
    """The configured gateway.

    Built per call rather than cached: the object is trivially cheap, and the
    expensive part -- the SMPP session -- is a process-wide singleton behind
    it. Caching here would only make settings changes in tests invisible.
    """
    from django.conf import settings

    name = getattr(settings, 'SMS_PROVIDER', '') or ''
    if not name:
        raise UnknownSmsProvider(
            'SMS_PROVIDER is not set. Production must set it to '
            "'timwe_smpp' explicitly -- there is no default gateway."
        )
    return _build(name)


def reset_gateway():
    """Drop the process's SMPP session. For worker shutdown and tests."""
    from api.integrations.smpp.client import reset_client

    reset_client()
