"""
Which gateway delivers application SMS.

Selected by ``settings.SMS_PROVIDER``. There is no fallback and no default
that reaches a real network: an unrecognised value raises rather than quietly
picking one, because the failure mode being avoided is production silently
sending over the retired OneVAS gateway after a config typo.

    timwe_smpp   the production transport
    console      logs instead of sending; local development only
    onevas_http  retired, explicit rollback only -- warns on every send
"""

from django.core.exceptions import ImproperlyConfigured

from api.services.sms.base import SmsGateway, SubmitResult

__all__ = ['SmsGateway', 'SubmitResult', 'UnknownSmsProvider', 'get_gateway', 'reset_gateway']


class UnknownSmsProvider(ImproperlyConfigured):
    """SMS_PROVIDER names a gateway that does not exist."""


def _build(name, **kwargs) -> SmsGateway:
    if name == 'timwe_smpp':
        from api.services.sms.timwe_smpp import TimweSmppGateway

        return TimweSmppGateway()
    if name == 'console':
        from api.services.sms.console import ConsoleGateway

        return ConsoleGateway()
    if name == 'onevas_http':
        from api.services.sms.onevas_http import OnevasHttpGateway

        return OnevasHttpGateway(tier_type=kwargs.get('tier_type'))
    raise UnknownSmsProvider(
        f'SMS_PROVIDER={name!r} is not a known gateway. '
        "Expected 'timwe_smpp' (production), 'console' (development), "
        "or 'onevas_http' (retired)."
    )


def get_gateway(**kwargs) -> SmsGateway:
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
    return _build(name, **kwargs)


def reset_gateway():
    """Drop the process's SMPP session. For worker shutdown and tests."""
    from api.integrations.smpp.client import reset_client

    reset_client()
