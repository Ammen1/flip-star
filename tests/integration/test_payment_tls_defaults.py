"""Audit H-02: payment TLS verification is on unless a deployment says otherwise.

``TELEBIRR_VERIFY_SSL`` defaulted to False. Nothing in ``k8s/`` set it, so every
environment that did not think about it -- production included -- sent third-party
credentials and payout instructions over a connection that was encrypted but not
authenticated. An on-path party could read and alter them.

The default is now True, staging opts out explicitly because the provider's UAT
endpoint serves a private certificate, and ``manage.py check`` reports
flipstar.W004 wherever it is off. These tests pin the direction of the default,
which is the part that must not silently flip back.
"""

import pytest
from django.conf import settings
from django.core.checks import run_checks

pytestmark = pytest.mark.integration


def _check_ids(**overrides):
    """Run the project's system checks and return the ids they reported."""
    return {m.id for m in run_checks()}


# ── the default direction ────────────────────────────────────────────────────


def test_telebirr_tls_verification_is_on_by_default():
    """The whole finding: forgetting the flag must mean secure, not insecure."""
    assert settings.TELEBIRR_VERIFY_SSL is True, (
        'H-02: TELEBIRR_VERIFY_SSL defaults to False again. A deployment that '
        'does not set it would send payment credentials over an unauthenticated '
        'connection.'
    )


def test_timwe_tls_verification_is_on_by_default():
    assert settings.TIMWE_CHARGE_VERIFY_TLS is True


def test_the_telebirr_client_follows_the_setting(settings):
    """The setting is only worth anything if the client reads it."""
    from api.integrations.telebirr.direct_debit import TelebirrDirectDebitService

    settings.TELEBIRR_VERIFY_SSL = True
    assert TelebirrDirectDebitService().verify_ssl is True

    settings.TELEBIRR_VERIFY_SSL = False
    assert TelebirrDirectDebitService().verify_ssl is False


def test_the_checkout_client_follows_the_setting(settings):
    from api.integrations.telebirr.checkout import TelebirrService

    settings.TELEBIRR_VERIFY_SSL = True
    assert TelebirrService().verify_ssl is True

    settings.TELEBIRR_VERIFY_SSL = False
    assert TelebirrService().verify_ssl is False


# ── turning it off stays visible ─────────────────────────────────────────────


def test_disabling_telebirr_verification_raises_a_check_warning(settings):
    settings.DEBUG = False
    settings.TELEBIRR_VERIFY_SSL = False
    assert 'flipstar.W004' in _check_ids()


def test_disabling_timwe_verification_raises_a_check_warning(settings):
    settings.DEBUG = False
    settings.TIMWE_CHARGE_VERIFY_TLS = False
    assert 'flipstar.W005' in _check_ids()


def test_no_tls_warning_when_both_are_verified(settings):
    settings.DEBUG = False
    settings.TELEBIRR_VERIFY_SSL = True
    settings.TIMWE_CHARGE_VERIFY_TLS = True
    ids = _check_ids()
    assert 'flipstar.W004' not in ids
    assert 'flipstar.W005' not in ids


def test_a_developer_machine_is_not_nagged(settings):
    """DEBUG means a laptop, where a private testbed cert is the normal case."""
    settings.DEBUG = True
    settings.TELEBIRR_VERIFY_SSL = False
    settings.TIMWE_CHARGE_VERIFY_TLS = False
    ids = _check_ids()
    assert 'flipstar.W004' not in ids
    assert 'flipstar.W005' not in ids


# ── the staging overlay is the documented exception ──────────────────────────


def test_staging_overlay_opts_out_explicitly_and_only_staging_does():
    """The exception must live in the overlay, not in the defaults."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    staging = (root / 'k8s/overlays/staging/patches/configmap-patch.yaml').read_text(
        encoding='utf-8'
    )
    assert (
        'TELEBIRR_VERIFY_SSL: "false"' in staging
    ), 'staging must opt out explicitly; relying on a false default is H-02'

    base = (root / 'k8s/base/configmap.yaml').read_text(encoding='utf-8')
    assert (
        'TELEBIRR_VERIFY_SSL' not in base
    ), 'the base ConfigMap must not set it -- that would apply to production too'

    production = (root / 'k8s/overlays/production/patches/configmap-patch.yaml').read_text(
        encoding='utf-8'
    )
    assert (
        'TELEBIRR_VERIFY_SSL: "false"' not in production
    ), 'production must never disable payment certificate verification'
