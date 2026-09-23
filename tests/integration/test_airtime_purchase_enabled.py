"""
Buying coins with airtime: the switch, and what it switches.

The feature is off by default and always has been -- "Ethio Telecom SIM cards
are only accessible for SMS OTP verification" -- so switching it on is a
per-environment decision (``TIMWE_AIRTIME_PURCHASE_ENABLED``, set in the
staging overlay, absent from base so production inherits False).

What these hold down is that the switch is honest in both directions:

* off, the endpoint refuses in the way it always has and the page is told not
  to offer the option;
* on **but unconfigured**, the page is still told not to offer it -- an Airtime
  button that can only answer "not configured" is worse than none, and the
  policy flag alone is not evidence that TIMWE credentials exist;
* on and configured, 10 ETB goes through the charging path that already
  exists, at the price the package carries, credited exactly once.

The 10 ETB rule itself is not tested here -- it belongs to
tests/unit/test_payment_methods.py and is unchanged -- beyond confirming that
this path still enforces it.

Nothing here prints a credential. ``missing_configuration()`` returns setting
*names*, which is what the operator check on staging relies on.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory

from api.models.contest import CoinPackage, CoinTransaction, UserCoinBalance
from api.models.timwe import TimweChargeTransaction
from api.services import airtime_purchase
from api.services.timwe_charging import purchase_coins_with_airtime

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()
MSISDN = '251911528271'

#: What chargeAmount cannot be built without. Values are test stand-ins.
CHARGE_CONFIG = {
    'TIMWE_CHARGE_URL': 'http://ma.test:8080/AmountChargingService/services/AmountCharging',
    'TIMWE_SP_ID': '000201',
    'TIMWE_SP_PASSWORD': 'account-password-for-tests',
    'TIMWE_SERVICE_ID': '3500001000012',
    'TIMWE_CURRENCY': 'ETB',
    'TIMWE_CHARGING_ENABLED': True,
}


@pytest.fixture
def charging_configured(settings):
    for key, value in CHARGE_CONFIG.items():
        setattr(settings, key, value)
    return settings


@pytest.fixture
def airtime_on(charging_configured):
    charging_configured.TIMWE_AIRTIME_PURCHASE_ENABLED = True
    return charging_configured


@pytest.fixture
def airtime_off(charging_configured):
    charging_configured.TIMWE_AIRTIME_PURCHASE_ENABLED = False
    return charging_configured


@pytest.fixture
def buyer():
    """Somebody who may buy coins: a phone on file and an active plan."""
    from datetime import timedelta

    from django.utils import timezone

    from api.models import SubscriptionTier
    from api.models.subscription import SubscriptionPlan

    user = User.objects.create_user(username='airtime_buyer', password='x')
    user.profile.phone_number = MSISDN
    user.profile.save(update_fields=['phone_number'])
    SubscriptionPlan.objects.create(
        user=user,
        tier=SubscriptionTier.objects.filter(duration_type='monthly').first(),
        status='active',
        start_date=timezone.now() - timedelta(days=1),
        end_date=timezone.now() + timedelta(days=30),
    )
    return user


@pytest.fixture
def ten_birr_package():
    package, _ = CoinPackage.objects.get_or_create(
        price_etb=Decimal('10'),
        defaults={'name': 'Starter', 'coin_amount': 100, 'bonus_coins': 0, 'is_active': True},
    )
    CoinPackage.objects.filter(pk=package.pk).update(is_active=True)
    package.refresh_from_db()
    return package


@pytest.fixture
def buy(encrypted_client_keys):
    """Call the purchase endpoint the way a real client does.

    It sits behind the E2E transport, so both the header and an *encrypted
    body* are required -- plaintext is refused by the parser before the view
    runs, which would make every one of these pass or fail for the wrong
    reason.
    """
    from rest_framework.test import APIClient

    from common.security.e2e_encryption import encrypt_payload

    server_public_key, public, private = encrypted_client_keys

    def _buy(user, idempotency_key='airtime-test-1', **body):
        body.setdefault('idempotency_key', idempotency_key)
        sealed = encrypt_payload(body, server_public_key, private)
        client = APIClient()
        client.force_authenticate(user=user)
        return client.post(
            '/api/v1/charging/coin-purchase/',
            sealed.to_dict(),
            format='json',
            HTTP_X_CLIENT_PUBLIC_KEY=public,
        )

    return _buy


def coins(user):
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.refresh_from_db()
    return balance.balance


# ── the switch ───────────────────────────────────────────────────────────────


def test_airtime_is_refused_while_the_flag_is_off(airtime_off, buyer, ten_birr_package, buy):
    """The behaviour every environment has today, unchanged."""
    before = coins(buyer)

    response = buy(buyer, package_id=ten_birr_package.id, price_etb='10')

    assert response.status_code == 403
    assert 'disabled' in response.data['error'].lower()
    assert 'SMS OTP verification' in response.data['error']
    assert coins(buyer) == before, 'a refusal must not move a balance'


def test_the_default_is_off(settings):
    """Production inherits this. Nothing in code turns it on."""
    for key, value in CHARGE_CONFIG.items():
        setattr(settings, key, value)
    del settings.TIMWE_AIRTIME_PURCHASE_ENABLED
    from django.conf import settings as live

    assert getattr(live, 'TIMWE_AIRTIME_PURCHASE_ENABLED', False) is False
    assert airtime_purchase.policy_enabled() is False


def test_the_flag_alone_does_not_make_it_available(settings):
    """Switched on in an environment with no charging credentials, the answer
    is still no -- offering a button that can only fail is worse than none."""
    settings.TIMWE_AIRTIME_PURCHASE_ENABLED = True
    settings.TIMWE_CHARGING_ENABLED = True
    settings.TIMWE_CHARGE_URL = ''
    settings.TIMWE_SP_ID = ''

    assert airtime_purchase.policy_enabled() is True
    assert airtime_purchase.is_available() is False


def test_the_reasons_name_settings_and_never_values(settings):
    settings.TIMWE_AIRTIME_PURCHASE_ENABLED = True
    settings.TIMWE_CHARGING_ENABLED = True
    settings.TIMWE_CHARGE_URL = ''
    settings.TIMWE_SP_PASSWORD = 'a-real-looking-secret'
    settings.TIMWE_SP_ID = '000201'
    settings.TIMWE_SERVICE_ID = '3500001000012'
    settings.TIMWE_CURRENCY = 'ETB'

    reasons = ' '.join(airtime_purchase.unavailable_reasons())

    assert 'TIMWE_CHARGE_URL' in reasons
    assert 'a-real-looking-secret' not in reasons, 'a credential leaked into the reasons'


def test_it_is_available_when_switched_on_and_configured(airtime_on):
    assert airtime_purchase.unavailable_reasons() == []
    assert airtime_purchase.is_available() is True


def test_the_master_charging_switch_still_applies(airtime_on):
    """Airtime purchase rides on the charging client; its own switch wins."""
    airtime_on.TIMWE_CHARGING_ENABLED = False

    assert airtime_purchase.is_available() is False


# ── what /wallet/config/ tells the page ──────────────────────────────────────


def config_body(user, keys):
    import json

    from django.urls import reverse
    from rest_framework.test import APIClient

    from common.security.e2e_encryption import decrypt_payload

    server_public_key, public, private = keys
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(reverse('wallet-public-config'), HTTP_X_CLIENT_PUBLIC_KEY=public)
    assert response.status_code == 200, response.status_code
    response.render()
    body = json.loads(response.content)
    if {'encrypted', 'nonce', 'checksum'} <= body.keys():
        body = json.loads(
            decrypt_payload(
                body['encrypted'], body['nonce'], server_public_key, body['checksum'], private
            )
        )
    return body


def test_the_config_says_no_while_the_flag_is_off(airtime_off, buyer, encrypted_client_keys):
    assert config_body(buyer, encrypted_client_keys)['allows_airtime'] is False


def test_the_config_says_yes_when_switched_on_and_configured(
    airtime_on, buyer, encrypted_client_keys
):
    assert config_body(buyer, encrypted_client_keys)['allows_airtime'] is True


def test_the_config_says_no_when_switched_on_but_unconfigured(
    airtime_on, buyer, encrypted_client_keys
):
    airtime_on.TIMWE_CHARGE_URL = ''

    assert config_body(buyer, encrypted_client_keys)['allows_airtime'] is False


def test_the_config_still_carries_everything_it_did(airtime_on, buyer, encrypted_client_keys):
    """Additive only: the page reads several of these."""
    body = config_body(buyer, encrypted_client_keys)

    for field in (
        'currency',
        'coins_per_birr',
        'custom_purchase',
        'costs',
        'packages',
        'post_costs',
        'withdrawal',
    ):
        assert field in body, f'{field} went missing from the config response'


def test_the_config_never_carries_a_credential(airtime_on, buyer, encrypted_client_keys):
    body = str(config_body(buyer, encrypted_client_keys))

    for secret in ('account-password-for-tests', '000201', '3500001000012'):
        assert secret not in body, 'a TIMWE credential reached the client'


# ── the purchase, once it is switched on ─────────────────────────────────────


def test_ten_birr_reaches_the_existing_charging_flow(airtime_on, buyer, ten_birr_package, buy):
    """Enabled, the endpoint stops refusing and hands off to the one charging
    implementation -- no second path was added."""
    with patch('api.services.timwe_charging.purchase_coins_with_airtime') as charge:
        charge.side_effect = RuntimeError('reached the charging flow')
        response = buy(buyer, package_id=ten_birr_package.id, price_etb='10')

    assert response.status_code != 403, response.data
    assert charge.called, 'the existing TIMWE charging flow was not reached'


@pytest.mark.parametrize('price', ['10', 10, '10.00'])
def test_ten_birr_passes_the_price_rule(airtime_on, buyer, ten_birr_package, price, buy):
    with patch('api.services.timwe_charging.purchase_coins_with_airtime') as charge:
        charge.side_effect = RuntimeError('reached the charging flow')
        response = buy(buyer, package_id=ten_birr_package.id, price_etb=price)

    assert response.status_code != 400, f'{price} was refused by the price rule'


@pytest.mark.parametrize('price', ['10.01', '25', '50', 100])
def test_a_dearer_purchase_is_still_refused(airtime_on, buyer, ten_birr_package, price, buy):
    """Unchanged: airtime is permitted only up to 10 ETB."""
    response = buy(buyer, package_id=ten_birr_package.id, price_etb=price)

    assert response.status_code == 400
    assert 'airtime' in str(response.data).lower()


def test_the_price_rule_holds_even_while_the_flag_is_off(airtime_off, buyer, ten_birr_package, buy):
    """Checked before the flag on purpose, so the constraint cannot be lost by
    a future change to the switch."""
    response = buy(buyer, package_id=ten_birr_package.id, price_etb='50')

    assert response.status_code == 400, 'the price rule was skipped'


# ── charging outcomes ────────────────────────────────────────────────────────


def test_missing_configuration_is_reported_never_pretended_away(
    airtime_on, buyer, ten_birr_package
):
    from api.integrations.timwe.errors import TimweConfigurationError

    airtime_on.TIMWE_CHARGE_URL = ''
    before = coins(buyer)

    with pytest.raises(TimweConfigurationError) as exc:
        purchase_coins_with_airtime(user=buyer, package=ten_birr_package, idempotency_key='cfg-1')

    assert 'TIMWE_CHARGE_URL' in str(exc.value)
    assert 'account-password-for-tests' not in str(exc.value), 'a credential leaked'
    assert coins(buyer) == before, 'coins were credited without a charge'


def test_a_failed_charge_credits_nothing(airtime_on, buyer, ten_birr_package):
    from api.services.timwe_charging import ChargeRefused

    before = coins(buyer)

    with patch('api.services.timwe_charging.request_charge') as charge:
        charge.side_effect = ChargeRefused('Insufficient airtime balance')
        with pytest.raises(ChargeRefused):
            purchase_coins_with_airtime(
                user=buyer, package=ten_birr_package, idempotency_key='fail-1'
            )

    assert coins(buyer) == before
    assert not CoinTransaction.objects.filter(
        user=buyer, transaction_type='purchase', coins__gt=0
    ).exists(), 'coins were credited for a charge that failed'


def test_a_successful_charge_credits_the_package_coins(airtime_on, buyer, ten_birr_package):
    before = coins(buyer)

    charge = TimweChargeTransaction.objects.create(
        user=buyer,
        msisdn=MSISDN,
        amount=Decimal('10'),
        currency='ETB',
        reference_code='ref-success-1',
        status='success',
        coin_package=ten_birr_package,
        purpose=TimweChargeTransaction.PURPOSE_COIN_PURCHASE,
    )

    from api.services.timwe_charging import fulfil_coin_purchase

    transaction = fulfil_coin_purchase(charge)

    assert transaction is not None
    assert coins(buyer) == before + ten_birr_package.get_total_coins()


def test_a_retried_request_charges_once(airtime_on, buyer, ten_birr_package, buy):
    """The client resends after a timeout with the same Idempotency-Key. The
    charge is not repeated and the coins are not credited twice."""
    with patch('api.services.timwe_charging.request_charge') as charge:
        from api.services.timwe_charging import ChargeRefused

        charge.side_effect = ChargeRefused('gateway said no')
        buy(buyer, package_id=ten_birr_package.id, idempotency_key='retry-me-1')
        buy(buyer, package_id=ten_birr_package.id, idempotency_key='retry-me-1')

    purchases = CoinTransaction.objects.filter(user=buyer, transaction_type='purchase', coins__gt=0)
    assert not purchases.exists(), 'a refused charge credited coins'


def test_the_same_charge_cannot_credit_twice(airtime_on, buyer, ten_birr_package):
    """A retried request, a redelivered callback, a double tap."""
    from api.services.timwe_charging import fulfil_coin_purchase

    charge = TimweChargeTransaction.objects.create(
        user=buyer,
        msisdn=MSISDN,
        amount=Decimal('10'),
        currency='ETB',
        reference_code='ref-once-1',
        status='success',
        coin_package=ten_birr_package,
        purpose=TimweChargeTransaction.PURPOSE_COIN_PURCHASE,
    )
    before = coins(buyer)

    first = fulfil_coin_purchase(charge)
    second = fulfil_coin_purchase(charge)
    third = fulfil_coin_purchase(charge)

    assert first is not None
    assert second is None and third is None, 'a second credit was allowed'
    assert coins(buyer) == before + ten_birr_package.get_total_coins()
