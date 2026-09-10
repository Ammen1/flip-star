"""
Who may reset a PIN by phone.

A reset is for a subscriber. A number with no account, or an account with no
active subscription, is told which -- and how to subscribe -- instead of the
old "if an account exists, you will receive a code", which left them waiting
for an SMS that was never sent.

Both steps enforce it. The OTP cache is shared with login, and
/auth/send-login-otp/ hands a code to any number, so a check on the request
step alone would let that code reset the PIN of an account it turned away.
"""

import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import fakeredis
import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from api.models.subscription import SubscriptionPlan, SubscriptionTier
from api.services.otp import OTPService
from api.views.core import forgot_password_phone_request, forgot_password_phone_verify
from common.security.e2e_encryption import decrypt_payload, encrypt_payload, generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()

PHONE = '251911223344'
LOCAL_PHONE = '0911223344'
NEW_PIN = '307942'


@pytest.fixture(autouse=True)
def _clean_cache():
    # Throttle counters and OTPs both live here.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def server_keys(db):
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def call(server_keys):
    """POST to a view over the encrypted transport the app uses."""
    client_public_key, client_private_key = generate_keypair()

    def _call(view, body):
        envelope = encrypt_payload(
            body,
            receiver_public_key_b64=server_keys,
            sender_private_key_b64=client_private_key,
        ).to_dict()
        request = factory.post(
            '/x',
            data=json.dumps(envelope),
            content_type='application/json',
            HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
        )
        response = view(request)
        response.render()
        sealed = json.loads(response.content)
        if 'encrypted' not in sealed:
            return response.status_code, sealed
        plaintext = decrypt_payload(
            sealed['encrypted'],
            sealed['nonce'],
            server_keys,
            sealed['checksum'],
            client_private_key,
        )
        return response.status_code, json.loads(plaintext)

    return _call


@pytest.fixture
def sms():
    with patch('api.services.sms.dispatch.queue_sms') as queued:
        yield queued


@pytest.fixture
def tier(db):
    return SubscriptionTier.objects.create(
        name='Daily Premium',
        slug='daily-premium',
        price_etb=Decimal('3.00'),
        duration_type='daily',
        duration_days=1,
        is_active=True,
    )


def _account(username='resetter'):
    user = User.objects.create_user(username=username, password='518273')
    user.profile.phone_number = PHONE
    user.profile.save()
    return user


def _subscribe(user, tier, *, ends_in=timedelta(days=1)):
    now = timezone.now()
    return SubscriptionPlan.objects.create(
        user=user,
        tier=tier,
        status='active',
        duration_type='daily',
        start_date=now - timedelta(days=1),
        end_date=now + ends_in,
    )


def _issue_code(code='482913'):
    """A live OTP for PHONE, as send_otp -- or send_login_otp -- leaves it."""
    cache.set(
        OTPService.get_otp_cache_key(PHONE),
        {
            'code': code,
            'expires_at': (timezone.now() + timedelta(minutes=5)).isoformat(),
            'attempts': 0,
        },
        timeout=300,
    )
    return code


def _assert_tells_how_to_subscribe(body):
    hint = body['subscribe_hint']
    assert '9286' in hint
    assert 'airtime' in hint
    assert 'telebirr' in hint


# ── requesting a code ────────────────────────────────────────────────────────


def test_a_number_with_no_account_is_told_so(call, sms):
    status_code, body = call(forgot_password_phone_request, {'phone': LOCAL_PHONE})

    assert status_code == 404
    assert body['code'] == 'USER_NOT_FOUND'
    assert 'No FlipStar account' in body['error']
    _assert_tells_how_to_subscribe(body)
    sms.assert_not_called()


def test_an_account_without_a_subscription_is_told_to_subscribe(call, sms):
    _account()

    status_code, body = call(forgot_password_phone_request, {'phone': LOCAL_PHONE})

    assert status_code == 403
    assert body['code'] == 'SUBSCRIPTION_REQUIRED'
    assert 'active subscription' in body['error']
    _assert_tells_how_to_subscribe(body)
    sms.assert_not_called()


def test_an_expired_subscription_is_no_subscription(call, sms, tier):
    """`status` can still read active after a failed renewal; the date decides."""
    _subscribe(_account(), tier, ends_in=-timedelta(hours=1))

    status_code, body = call(forgot_password_phone_request, {'phone': LOCAL_PHONE})

    assert status_code == 403
    assert body['code'] == 'SUBSCRIPTION_REQUIRED'
    sms.assert_not_called()


def test_a_subscriber_gets_a_reset_code(call, sms, tier):
    _subscribe(_account(), tier)

    status_code, body = call(forgot_password_phone_request, {'phone': LOCAL_PHONE})

    assert status_code == 200, body
    sms.assert_called_once()
    assert sms.call_args.kwargs['phone_number'] == PHONE
    assert sms.call_args.kwargs['purpose'] == 'otp_password_reset'


# ── using the code ───────────────────────────────────────────────────────────


def test_a_valid_code_does_not_reset_a_non_subscribers_pin(call):
    """The login OTP route gives any number a code; it must not open this door."""
    user = _account()
    code = _issue_code()

    status_code, body = call(
        forgot_password_phone_verify,
        {'phone': LOCAL_PHONE, 'code': code, 'new_password': NEW_PIN},
    )

    assert status_code == 403
    assert body['code'] == 'SUBSCRIPTION_REQUIRED'
    user.refresh_from_db()
    assert not user.check_password(NEW_PIN)


def test_an_unknown_number_cannot_reset(call):
    code = _issue_code()

    status_code, body = call(
        forgot_password_phone_verify,
        {'phone': LOCAL_PHONE, 'code': code, 'new_password': NEW_PIN},
    )

    assert status_code == 404
    assert body['code'] == 'USER_NOT_FOUND'


def test_a_subscriber_resets_their_pin(call, tier):
    user = _account()
    _subscribe(user, tier)
    code = _issue_code()

    status_code, body = call(
        forgot_password_phone_verify,
        {'phone': LOCAL_PHONE, 'code': code, 'new_password': NEW_PIN},
    )

    assert status_code == 200, body
    user.refresh_from_db()
    assert user.check_password(NEW_PIN)


def test_a_subscriber_with_a_wrong_code_keeps_their_pin(call, tier):
    user = _account()
    _subscribe(user, tier)
    _issue_code('482913')

    status_code, body = call(
        forgot_password_phone_verify,
        {'phone': LOCAL_PHONE, 'code': '000111', 'new_password': NEW_PIN},
    )

    assert status_code == 400
    assert 'Invalid OTP' in body['error']
    user.refresh_from_db()
    assert not user.check_password(NEW_PIN)
