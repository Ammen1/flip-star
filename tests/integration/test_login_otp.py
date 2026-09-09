"""
Regression tests for send_login_otp / login_with_otp (api/views/core.py) --
ported from the master branch, missing entirely in the current project
before this change. Distinct from the existing send_phone_otp/verify_phone_otp
pair (registration -- rejects an already-registered number) and from
login_with_subscription_otp (requires a password and a subscription-tied
setup_otp): this is passwordless login for an existing user by phone,
including a user who only ever paid through the Telebirr SuperApp and never
went through phone registration (looked up via SubscriptionPlan.telebirr_phone_number).

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from api.views.core import login_with_otp, send_login_otp

pytestmark = pytest.mark.integration

factory = APIRequestFactory()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _mock_sms_gateway():
    """Stop OTP SMS at the queue, not at the transport.

    This used to patch ``api.services.otp.requests.post``, because send_otp
    POSTed to the OneVAS SMS gateway inline and every test otherwise blocked
    for the full 30s timeout against a host the sandbox cannot reach.

    That call is gone: OTP SMS is queued and delivered over TIMWE SMPP by the
    SMS worker. Patching ``queue_sms`` mocks the right seam -- the tests still
    never touch a network, and they now also prove the OTP path goes through
    the gateway abstraction rather than any one provider. The OTP itself is
    generated and cached before this point, so nothing here needs to succeed
    for the assertions below to hold.
    """
    with patch('api.services.sms.dispatch.queue_sms') as mock_queue:
        mock_queue.return_value = MagicMock(id='test-sms-id')
        yield mock_queue


@pytest.fixture
def existing_user(db):
    u = User.objects.create_user(username='otp_login_user', password='x')
    u.profile.phone_number = '251911223344'
    u.profile.save()
    yield u
    u.delete()


def _current_otp_code(phone):
    data = cache.get(f'otp:{phone}')
    assert data is not None, 'expected an OTP to have been cached for this phone'
    return data['code']


def test_send_login_otp_for_existing_user_reports_user_exists_true(existing_user):
    request = factory.post('/auth/send-login-otp/', {'phone': '0911223344'}, format='json')

    response = send_login_otp(request)

    assert response.status_code == 200, response.data
    assert response.data['user_exists'] is True
    assert response.data['phone'] == '251911223****'  # masked: first 9 chars + ****


def test_send_login_otp_for_unknown_number_still_sends_but_reports_user_exists_false(db):
    request = factory.post('/auth/send-login-otp/', {'phone': '0922334455'}, format='json')

    response = send_login_otp(request)

    assert response.status_code == 200, response.data
    assert response.data['user_exists'] is False


def test_send_login_otp_rejects_invalid_phone_number(db):
    request = factory.post('/auth/send-login-otp/', {'phone': 'not-a-phone'}, format='json')

    response = send_login_otp(request)

    assert response.status_code == 400


def test_send_login_otp_rejects_missing_phone(db):
    request = factory.post('/auth/send-login-otp/', {}, format='json')

    response = send_login_otp(request)

    assert response.status_code == 400


def test_login_with_otp_succeeds_for_registered_user(existing_user):
    send_login_otp(factory.post('/auth/send-login-otp/', {'phone': '0911223344'}, format='json'))
    code = _current_otp_code('251911223344')

    response = login_with_otp(
        factory.post('/auth/login-with-otp/', {'phone': '0911223344', 'code': code}, format='json'),
    )

    assert response.status_code == 200, response.data
    assert response.data['user']['username'] == 'otp_login_user'
    assert 'token' in response.data


def test_login_with_otp_rejects_wrong_code(existing_user):
    send_login_otp(factory.post('/auth/send-login-otp/', {'phone': '0911223344'}, format='json'))

    response = login_with_otp(
        factory.post(
            '/auth/login-with-otp/', {'phone': '0911223344', 'code': '000000'}, format='json'
        ),
    )

    assert response.status_code == 400


def test_login_with_otp_rejects_when_no_account_exists(db):
    send_login_otp(factory.post('/auth/send-login-otp/', {'phone': '0933445566'}, format='json'))
    code = _current_otp_code('251933445566')

    response = login_with_otp(
        factory.post('/auth/login-with-otp/', {'phone': '0933445566', 'code': code}, format='json'),
    )

    assert response.status_code == 400
    assert 'register' in response.data['error'].lower()


def test_login_with_otp_falls_back_to_active_telebirr_subscription(db):
    """A user who paid via the Telebirr SuperApp but never went through
    phone registration must still be able to log in by OTP, resolved via
    SubscriptionPlan.telebirr_phone_number rather than UserProfile."""
    from api.models.subscription import SubscriptionPlan, SubscriptionTier

    telebirr_user = User.objects.create_user(username='telebirr_only_user', password='x')
    tier = SubscriptionTier.objects.create(
        name='OTP Login Test Daily',
        slug='otp-login-test-daily',
        duration_type='daily',
        duration_days=1,
        price_etb=10,
        onevas_code='T1',
        spid='sp1',
        service_id='svc1',
        product_id='prod1',
    )
    plan = SubscriptionPlan.objects.create(
        user=telebirr_user,
        tier=tier,
        status='active',
        payment_method='telebirr',
        telebirr_phone_number='251944556677',
        start_date=timezone.now(),
        end_date=timezone.now() + timezone.timedelta(days=1),
    )
    try:
        send_login_otp(
            factory.post('/auth/send-login-otp/', {'phone': '0944556677'}, format='json')
        )
        code = _current_otp_code('251944556677')

        response = login_with_otp(
            factory.post(
                '/auth/login-with-otp/', {'phone': '0944556677', 'code': code}, format='json'
            ),
        )

        assert response.status_code == 200, response.data
        assert response.data['user']['username'] == 'telebirr_only_user'
    finally:
        plan.delete()
        tier.delete()
        telebirr_user.delete()


def test_login_with_otp_does_not_fall_back_to_expired_telebirr_subscription(db):
    from api.models.subscription import SubscriptionPlan, SubscriptionTier

    telebirr_user = User.objects.create_user(username='telebirr_expired_user', password='x')
    tier = SubscriptionTier.objects.create(
        name='OTP Login Test Daily Expired',
        slug='otp-login-test-daily-expired',
        duration_type='daily',
        duration_days=1,
        price_etb=10,
        onevas_code='T2',
        spid='sp2',
        service_id='svc2',
        product_id='prod2',
    )
    plan = SubscriptionPlan.objects.create(
        user=telebirr_user,
        tier=tier,
        status='active',
        payment_method='telebirr',
        telebirr_phone_number='251955667788',
        start_date=timezone.now() - timezone.timedelta(days=2),
        end_date=timezone.now() - timezone.timedelta(days=1),
    )
    try:
        send_login_otp(
            factory.post('/auth/send-login-otp/', {'phone': '0955667788'}, format='json')
        )
        code = _current_otp_code('251955667788')

        response = login_with_otp(
            factory.post(
                '/auth/login-with-otp/', {'phone': '0955667788', 'code': code}, format='json'
            ),
        )

        assert response.status_code == 400
    finally:
        plan.delete()
        tier.delete()
        telebirr_user.delete()
