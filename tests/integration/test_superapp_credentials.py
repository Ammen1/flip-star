"""
OneVAS credentials must not reach the client.

check_superapp_subscription is unauthenticated -- it has to be, the caller is
deciding whether to show a login prompt and holds no token. It used to return
application_key and product_number so PhoneLoginModal could post them back to
send-login-otp, which meant a provisioned secret (ONEVAS_<TIER>_APPLICATION_KEY,
resolved through Vault) was handed to anyone who knew a subscribed phone
number, and send_login_otp then trusted whatever the caller sent over the
configured value.

These tests pin both halves of the fix: the key is never serialised, and the
OTP path ignores a client-supplied one.
"""

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from api.models import SubscriptionPlan, SubscriptionTier
from api.views.core import send_login_otp
from api.views.subscription import check_superapp_subscription

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()

PHONE_LOCAL = '0988990011'
PHONE_E164 = '251988990011'

TIER_KEY = 'tier-specific-key-should-never-be-serialised'
ATTACKER_KEY = 'attacker-supplied-key'


@pytest.fixture
def monthly_tier():
    return SubscriptionTier.objects.create(
        name='Monthly Premium',
        slug='monthly-premium-creds',
        duration_type='monthly',
        duration_days=30,
        price_etb=100,
        onevas_code='CREDMONTHLY',
    )


@pytest.fixture
def active_subscription(monthly_tier):
    now = timezone.now()
    return SubscriptionPlan.objects.create(
        user=None,
        tier=monthly_tier,
        status='active',
        duration_type='monthly',
        start_date=now,
        end_date=now + timezone.timedelta(days=30),
        payment_method='telebirr',
        telebirr_phone_number=PHONE_E164,
        auto_renew=False,
    )


@pytest.fixture
def onevas_products(settings):
    settings.ONEVAS_PRODUCTS = {
        'monthly': {'application_key': TIER_KEY, 'product_id': 'tier-product-id'},
    }
    settings.ONEVAS_APPLICATION_KEY = 'default-key'
    settings.ONEVAS_PRODUCT_NUMBER = 'default-product'
    return settings


# ---------------------------------------------------------------------------
# check_superapp_subscription
# ---------------------------------------------------------------------------


def test_check_superapp_does_not_return_credentials(active_subscription, onevas_products):
    request = factory.post('/subscription/check-superapp/', {'phone': PHONE_LOCAL}, format='json')

    response = check_superapp_subscription(request)

    assert response.status_code == 200
    assert response.data['has_active_subscription'] is True
    assert 'application_key' not in response.data
    assert 'product_number' not in response.data
    # Belt and braces: the key must not appear under any other name either.
    assert TIER_KEY not in str(response.data)


def test_check_superapp_still_reports_subscription_state(active_subscription, onevas_products):
    """The fields the login flow actually needs are untouched."""
    request = factory.post('/subscription/check-superapp/', {'phone': PHONE_LOCAL}, format='json')

    response = check_superapp_subscription(request)

    assert response.data['has_active_subscription'] is True
    assert response.data['user_exists'] is False
    assert response.data['tier_type'] == 'monthly'


def test_check_superapp_reports_no_subscription_without_leaking(db, onevas_products):
    request = factory.post('/subscription/check-superapp/', {'phone': '0900000000'}, format='json')

    response = check_superapp_subscription(request)

    assert response.status_code == 200
    assert response.data['has_active_subscription'] is False
    assert TIER_KEY not in str(response.data)


# ---------------------------------------------------------------------------
# send_login_otp
# ---------------------------------------------------------------------------


def test_send_login_otp_ignores_client_supplied_application_key(
    active_subscription, onevas_products, monkeypatch
):
    """
    The whole point of the fix: a caller cannot choose which credential the
    server presents to OneVAS.
    """
    seen = {}

    def fake_send_otp(phone_number, application_key, product_number=None, action='verification'):
        seen['application_key'] = application_key
        seen['product_number'] = product_number
        return True, 'sent'

    monkeypatch.setattr('api.services.otp.OTPService.send_otp', staticmethod(fake_send_otp))

    request = factory.post(
        '/auth/send-login-otp/',
        {
            'phone': PHONE_LOCAL,
            'application_key': ATTACKER_KEY,
            'product_number': 'attacker-product',
        },
        format='json',
    )

    response = send_login_otp(request)

    assert response.status_code == 200
    assert seen['application_key'] == TIER_KEY
    assert seen['application_key'] != ATTACKER_KEY
    assert seen['product_number'] == 'tier-product-id'


def test_send_login_otp_resolves_the_tier_key_when_none_is_supplied(
    active_subscription, onevas_products, monkeypatch
):
    seen = {}

    def fake_send_otp(phone_number, application_key, product_number=None, action='verification'):
        seen['application_key'] = application_key
        return True, 'sent'

    monkeypatch.setattr('api.services.otp.OTPService.send_otp', staticmethod(fake_send_otp))

    request = factory.post('/auth/send-login-otp/', {'phone': PHONE_LOCAL}, format='json')

    response = send_login_otp(request)

    assert response.status_code == 200
    assert seen['application_key'] == TIER_KEY


def test_send_login_otp_falls_back_to_defaults_without_a_subscription(
    db, onevas_products, monkeypatch
):
    """An ordinary login, no SuperApp subscription behind the number."""
    seen = {}

    def fake_send_otp(phone_number, application_key, product_number=None, action='verification'):
        seen['application_key'] = application_key
        seen['product_number'] = product_number
        return True, 'sent'

    monkeypatch.setattr('api.services.otp.OTPService.send_otp', staticmethod(fake_send_otp))

    request = factory.post('/auth/send-login-otp/', {'phone': '0900000000'}, format='json')

    response = send_login_otp(request)

    assert response.status_code == 200
    assert seen['application_key'] == 'default-key'
    assert seen['product_number'] == 'default-product'
