"""
Regression tests for the SuperApp/USSD subscription views (api/views/subscription.py)
-- ported from the master branch, entirely missing in the current project
before this change: check_superapp_subscription, validate_subscription_token,
telebirr_ussd_subscription_initiate/status/webhook, plus
TelebirrDirectDebitService.initiate_ussd_push_payment
(api/integrations/telebirr/direct_debit.py).

The central requirement being tested, matching the rest of this project's
Telebirr-adjacent work: telebirr_ussd_subscription_initiate only ever
creates a 'pending' subscription; only telebirr_ussd_subscription_webhook,
once Telebirr's own callback confirms the payment, may activate it. Unlike
master's webhook (no locking at all), this uses select_for_update() +
transaction.atomic(), matching the established pattern elsewhere in this
codebase.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import fakeredis
import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from api.models.subscription import SubscriptionPayment, SubscriptionPlan, SubscriptionTier
from api.views.core import login_with_subscription_otp
from api.views.subscription import (
    check_superapp_subscription,
    telebirr_ussd_subscription_initiate,
    telebirr_ussd_subscription_status,
    telebirr_ussd_subscription_webhook,
    validate_subscription_token,
)
from common.security.e2e_encryption import encrypt_payload, generate_keypair
from infrastructure.keys import redis_store
from tests.conftest import verified_push_session

pytestmark = pytest.mark.integration

factory = APIRequestFactory()
plain_factory = RequestFactory()


# telebirr_ussd_subscription_initiate carries @encrypted_endpoint: api.js puts
# "/subscription/" in ENCRYPTED_ENDPOINT_PREFIXES, so the real client seals
# this body. Calling the view with a plain dict reproduces 59223b6f's bug
# rather than the production path, so these tests seal it the same way.
#
# Helpers mirror tests/integration/test_b2c_payout.py; this project keeps them
# per-file rather than in a shared conftest.


@pytest.fixture
def _server_keys(db):
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def client_keys():
    return generate_keypair()


@pytest.fixture(autouse=True)
def _clear_throttles():
    """Throttle counters live in the cache and are keyed by IP.

    login_with_subscription_otp is rate limited now, and every test here calls
    it from the same address, so without this the fifth test in a run starts
    getting 429s that have nothing to do with what it is testing.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _post_encrypted(url, body, *, server_public_key, client_keys, view):
    """Seal `body` for the server and invoke `view`, as the client does."""
    client_public_key, client_private_key = client_keys
    sealed = encrypt_payload(
        body,
        receiver_public_key_b64=server_public_key,
        sender_private_key_b64=client_private_key,
    )
    request = factory.post(
        url,
        data=json.dumps(sealed.to_dict()),
        content_type='application/json',
        HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
    )
    return view(request)


def _post_initiate(body, *, server_public_key, client_keys):
    return _post_encrypted(
        '/subscription/telebirr/ussd/initiate/',
        body,
        server_public_key=server_public_key,
        client_keys=client_keys,
        view=telebirr_ussd_subscription_initiate,
    )


def _get_encrypted(url, *, client_keys, view):
    """
    GET an @encrypted_endpoint view the way the client does.

    No request envelope -- there is no body -- but X-Client-Public-Key is
    still required, because the decorator seals the RESPONSE. Without it the
    view answers 400 "Missing required X-Client-Public-Key header." before
    running. Assertions still read response.data: DRF holds the plain dict
    until render time, and the renderer encrypts after that.
    """
    client_public_key, _ = client_keys
    request = plain_factory.get(url, HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)
    return view(request)


@pytest.fixture
def monthly_tier(db):
    tier = SubscriptionTier.objects.create(
        name='USSD Test Monthly',
        slug='ussd-test-monthly',
        duration_type='monthly',
        duration_days=30,
        price_etb=150,
        onevas_code='U1',
        spid='sp',
        service_id='svc',
        product_id='prod',
        is_active=True,
    )
    yield tier
    tier.delete()


def _soap_result(*, originator_conversation_id, result_code, transaction_id='', result_desc=''):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:res="http://cps.huawei.com/cpsinterface/result">
  <soapenv:Body>
    <api:Result xmlns:api="http://cps.huawei.com/cpsinterface/api_resultmgr">
      <res:Header>
        <res:OriginatorConversationID>{originator_conversation_id}</res:OriginatorConversationID>
        <res:ConversationID>AG1</res:ConversationID>
      </res:Header>
      <res:Body>
        <res:ResultType>{'0' if result_code == '0' else '1'}</res:ResultType>
        <res:ResultCode>{result_code}</res:ResultCode>
        <res:ResultDesc>{result_desc}</res:ResultDesc>
        <res:TransactionResult>
          <res:TransactionID>{transaction_id}</res:TransactionID>
        </res:TransactionResult>
      </res:Body>
    </api:Result>
  </soapenv:Body>
</soapenv:Envelope>""".encode()


# ---------------------------------------------------------------------------
# telebirr_ussd_subscription_initiate: never activates directl
# ---------------------------------------------------------------------------


def test_initiate_creates_pending_subscription_not_active(
    db, monthly_tier, _server_keys, client_keys
):
    with patch(
        'api.views.subscription.telebirr_direct_debit_service.initiate_ussd_push_payment',
        return_value={
            'success': True,
            'originator_conversation_id': 'S_X_USSD1',
            'conversation_id': 'AG_USSD1',
        },
    ):
        response = _post_initiate(
            {
                'tier_id': str(monthly_tier.id),
                'phone_number': '0911223344',
                # A USSD Push now needs a verified number behind it.
                'verification_session_id': str(
                    verified_push_session(
                        phone_number='0911223344', tier_id=str(monthly_tier.id)
                    ).id
                ),
            },
            server_public_key=_server_keys,
            client_keys=client_keys,
        )

    assert response.status_code == 200, response.data
    payment = SubscriptionPayment.objects.get(onevas_transaction_id='S_X_USSD1')
    assert payment.status == 'pending'
    assert payment.subscription.status == 'pending'
    assert payment.subscription.status != 'active'


def test_initiate_requires_phone_for_anonymous_user(db, monthly_tier, _server_keys, client_keys):
    response = _post_initiate(
        {'tier_id': str(monthly_tier.id)},
        server_public_key=_server_keys,
        client_keys=client_keys,
    )

    # 400 for the missing phone, not for a body the view could not read.
    assert response.status_code == 400
    assert 'Phone number' in str(response.data)


def test_initiate_rejects_unknown_tier(db, _server_keys, client_keys):
    response = _post_initiate(
        {
            'tier_id': '00000000-0000-0000-0000-000000000000',
            'phone_number': '0911223344',
        },
        server_public_key=_server_keys,
        client_keys=client_keys,
    )

    assert response.status_code == 404


def test_initiate_returns_error_when_telebirr_call_fails(
    db, monthly_tier, _server_keys, client_keys
):
    with patch(
        'api.views.subscription.telebirr_direct_debit_service.initiate_ussd_push_payment',
        return_value={'success': False, 'error': 'upstream down'},
    ):
        response = _post_initiate(
            {
                'tier_id': str(monthly_tier.id),
                'phone_number': '0911223344',
                # A USSD Push now needs a verified number behind it.
                'verification_session_id': str(
                    verified_push_session(
                        phone_number='0911223344', tier_id=str(monthly_tier.id)
                    ).id
                ),
            },
            server_public_key=_server_keys,
            client_keys=client_keys,
        )

    assert response.status_code == 500
    assert not SubscriptionPayment.objects.filter(subscription__tier=monthly_tier).exists()


# ---------------------------------------------------------------------------
# telebirr_ussd_subscription_webhook: only place that activates
# ---------------------------------------------------------------------------


@pytest.fixture
def pending_ussd_payment(db, monthly_tier):
    start = timezone.now()
    end = start + timezone.timedelta(days=30)
    subscription = SubscriptionPlan.objects.create(
        user=None,
        tier=monthly_tier,
        status='pending',
        duration_type='monthly',
        start_date=start,
        end_date=end,
        payment_method='telebirr',
        auto_renew=False,
    )
    payment = SubscriptionPayment.objects.create(
        user=None,
        subscription=subscription,
        amount=monthly_tier.price_etb,
        currency='ETB',
        status='pending',
        payment_method='telebirr',
        onevas_transaction_id='S_X_USSDWEBHOOK1',
        duration_type='monthly',
        period_start=start,
        period_end=end,
        metadata={'phone_number': '251966778899'},
    )
    yield payment
    payment.delete()
    subscription.delete()


def test_webhook_activates_pending_subscription_and_creates_user(pending_ussd_payment):
    body = _soap_result(
        originator_conversation_id='S_X_USSDWEBHOOK1', result_code='0', transaction_id='TXNUSSD1'
    )
    request = plain_factory.post(
        '/webhooks/telebirrSubscriptionUssd/', data=body, content_type='text/xml'
    )

    with patch('api.services.otp.OTPService.send_otp', return_value=(True, 'ok')):
        response = telebirr_ussd_subscription_webhook(request)

    assert response.status_code == 200

    pending_ussd_payment.refresh_from_db()
    assert pending_ussd_payment.status == 'completed'
    assert pending_ussd_payment.subscription.status == 'active'
    assert pending_ussd_payment.user is not None
    assert pending_ussd_payment.user.profile.phone_number == '251966778899'


def test_webhook_marks_payment_failed_on_telebirr_failure(pending_ussd_payment):
    body = _soap_result(
        originator_conversation_id='S_X_USSDWEBHOOK1', result_code='1', result_desc='declined'
    )
    request = plain_factory.post(
        '/webhooks/telebirrSubscriptionUssd/', data=body, content_type='text/xml'
    )

    response = telebirr_ussd_subscription_webhook(request)

    assert response.status_code == 200
    pending_ussd_payment.refresh_from_db()
    assert pending_ussd_payment.status == 'failed'
    assert pending_ussd_payment.subscription.status == 'pending'
    assert pending_ussd_payment.subscription.status != 'active'


def test_webhook_duplicate_delivery_does_not_double_activate(pending_ussd_payment):
    body = _soap_result(
        originator_conversation_id='S_X_USSDWEBHOOK1', result_code='0', transaction_id='TXNUSSD2'
    )

    with patch('api.services.otp.OTPService.send_otp', return_value=(True, 'ok')):
        telebirr_ussd_subscription_webhook(
            plain_factory.post(
                '/webhooks/telebirrSubscriptionUssd/', data=body, content_type='text/xml'
            )
        )
        first_user_id = SubscriptionPayment.objects.get(pk=pending_ussd_payment.pk).user_id

        telebirr_ussd_subscription_webhook(
            plain_factory.post(
                '/webhooks/telebirrSubscriptionUssd/', data=body, content_type='text/xml'
            )
        )

    pending_ussd_payment.refresh_from_db()
    assert pending_ussd_payment.status == 'completed'
    assert pending_ussd_payment.user_id == first_user_id


def test_webhook_reuses_existing_user_matched_by_phone(db, monthly_tier):
    existing_user = User.objects.create_user(username='ussd_existing_user', password='x')
    existing_user.profile.phone_number = '251977889900'
    existing_user.profile.save()

    start = timezone.now()
    end = start + timezone.timedelta(days=30)
    subscription = SubscriptionPlan.objects.create(
        user=None,
        tier=monthly_tier,
        status='pending',
        duration_type='monthly',
        start_date=start,
        end_date=end,
        payment_method='telebirr',
        auto_renew=False,
    )
    payment = SubscriptionPayment.objects.create(
        user=None,
        subscription=subscription,
        amount=monthly_tier.price_etb,
        currency='ETB',
        status='pending',
        payment_method='telebirr',
        onevas_transaction_id='S_X_USSDWEBHOOK2',
        duration_type='monthly',
        period_start=start,
        period_end=end,
        metadata={'phone_number': '251977889900'},
    )
    try:
        body = _soap_result(
            originator_conversation_id='S_X_USSDWEBHOOK2',
            result_code='0',
            transaction_id='TXNUSSD3',
        )

        with patch('api.services.otp.OTPService.send_otp', return_value=(True, 'ok')):
            telebirr_ussd_subscription_webhook(
                plain_factory.post(
                    '/webhooks/telebirrSubscriptionUssd/', data=body, content_type='text/xml'
                )
            )

        payment.refresh_from_db()
        assert payment.user_id == existing_user.id
        assert not User.objects.filter(username__startswith='user_251977889900').exists()
    finally:
        payment.delete()
        subscription.delete()
        existing_user.delete()


# ---------------------------------------------------------------------------
# telebirr_ussd_subscription_status: anonymous polling
# ---------------------------------------------------------------------------


def test_status_returns_found_false_for_unknown_id(db, _server_keys, client_keys):
    response = _get_encrypted(
        '/subscription/telebirr/ussd/status/?originator_conversation_id=nope',
        client_keys=client_keys,
        view=telebirr_ussd_subscription_status,
    )

    assert response.status_code == 200
    assert response.data['found'] is False


def test_status_reflects_pending_payment(pending_ussd_payment, _server_keys, client_keys):
    response = _get_encrypted(
        f'/subscription/telebirr/ussd/status/?originator_conversation_id={pending_ussd_payment.onevas_transaction_id}',
        client_keys=client_keys,
        view=telebirr_ussd_subscription_status,
    )

    assert response.status_code == 200
    assert response.data['found'] is True
    assert response.data['status'] == 'pending'
    assert response.data['subscription_status'] == 'pending'


def test_status_requires_originator_conversation_id(db, _server_keys, client_keys):
    response = _get_encrypted(
        '/subscription/telebirr/ussd/status/',
        client_keys=client_keys,
        view=telebirr_ussd_subscription_status,
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# check_superapp_subscription / validate_subscription_token
# ---------------------------------------------------------------------------


def test_check_superapp_subscription_finds_active_telebirr_subscription(db, monthly_tier):
    now = timezone.now()
    subscription = SubscriptionPlan.objects.create(
        user=None,
        tier=monthly_tier,
        status='active',
        duration_type='monthly',
        start_date=now,
        end_date=now + timezone.timedelta(days=30),
        payment_method='telebirr',
        telebirr_phone_number='251988990011',
        auto_renew=False,
    )
    try:
        request = factory.post(
            '/subscription/check-superapp/', {'phone': '0988990011'}, format='json'
        )

        response = check_superapp_subscription(request)

        assert response.status_code == 200
        assert response.data['has_active_subscription'] is True
        assert response.data['user_exists'] is False
    finally:
        subscription.delete()


def test_check_superapp_subscription_finds_locally_stored_phone(db, monthly_tier):
    now = timezone.now()
    subscription = SubscriptionPlan.objects.create(
        user=None,
        tier=monthly_tier,
        status='active',
        duration_type='monthly',
        start_date=now,
        end_date=now + timezone.timedelta(days=30),
        payment_method='telebirr',
        telebirr_phone_number='0988990011',
        auto_renew=False,
    )
    try:
        request = factory.post(
            '/subscription/check-superapp/', {'phone': '+251988990011'}, format='json'
        )

        response = check_superapp_subscription(request)

        assert response.status_code == 200
        assert response.data['has_active_subscription'] is True
    finally:
        subscription.delete()


def test_check_superapp_subscription_accepts_active_open_ended_plan(db, monthly_tier):
    subscription = SubscriptionPlan.objects.create(
        user=None,
        tier=monthly_tier,
        status='active',
        duration_type='monthly',
        start_date=timezone.now(),
        end_date=None,
        payment_method='telebirr',
        telebirr_phone_number='251988990011',
        auto_renew=True,
    )
    try:
        request = factory.post(
            '/subscription/check-superapp/', {'phone': '0988990011'}, format='json'
        )

        response = check_superapp_subscription(request)

        assert response.status_code == 200
        assert response.data['has_active_subscription'] is True
    finally:
        subscription.delete()


def test_check_superapp_subscription_no_match(db):
    request = factory.post('/subscription/check-superapp/', {'phone': '0900000000'}, format='json')

    response = check_superapp_subscription(request)

    assert response.status_code == 200
    assert response.data['has_active_subscription'] is False


def test_subscription_otp_creates_web_account_for_superapp_phone(
    db, monthly_tier, _server_keys, client_keys
):
    now = timezone.now()
    subscription = SubscriptionPlan.objects.create(
        user=None,
        tier=monthly_tier,
        status='active',
        duration_type='monthly',
        start_date=now,
        end_date=now + timezone.timedelta(days=30),
        payment_method='telebirr',
        telebirr_phone_number='251988990011',
        setup_otp='123456',
        # Issued codes carry an expiry, and the login endpoint enforces it.
        setup_otp_expires_at=now + timezone.timedelta(minutes=30),
        auto_renew=False,
    )
    try:
        response = _post_encrypted(
            '/auth/login-with-subscription-otp/',
            {
                'phone': '+251988990011',
                'otp': '123456',
                'username': 'superapp_web_user',
                'password': '739284',
            },
            server_public_key=_server_keys,
            client_keys=client_keys,
            view=login_with_subscription_otp,
        )

        assert response.status_code == 201, response.data
        assert response.data['user']['username'] == 'superapp_web_user'
        assert response.data['token']
        subscription.refresh_from_db()
        assert subscription.user.username == 'superapp_web_user'
        assert subscription.setup_otp is None
        assert subscription.user.check_password('739284')
    finally:
        subscription.delete()


def test_subscription_otp_sets_first_pin_for_existing_superapp_user(
    db, monthly_tier, _server_keys, client_keys
):
    user = User.objects.create_user(username='superapp_without_pin', password=None)
    now = timezone.now()
    subscription = SubscriptionPlan.objects.create(
        user=user,
        tier=monthly_tier,
        status='active',
        duration_type='monthly',
        start_date=now,
        end_date=now + timezone.timedelta(days=30),
        payment_method='telebirr',
        telebirr_phone_number='251988990011',
        setup_otp='123456',
        # Issued codes carry an expiry, and the login endpoint enforces it.
        setup_otp_expires_at=now + timezone.timedelta(minutes=30),
        auto_renew=False,
    )
    try:
        response = _post_encrypted(
            '/auth/login-with-subscription-otp/',
            {
                'phone': '+251988990011',
                'otp': '123456',
                'password': '739284',
            },
            server_public_key=_server_keys,
            client_keys=client_keys,
            view=login_with_subscription_otp,
        )

        assert response.status_code == 200, response.data
        assert response.data['token']
        user.refresh_from_db()
        assert user.check_password('739284')
        subscription.refresh_from_db()
        assert subscription.setup_otp is None
    finally:
        subscription.delete()
        user.delete()


def test_validate_subscription_token_returns_phone(db, monthly_tier, _server_keys, client_keys):
    now = timezone.now()
    subscription = SubscriptionPlan.objects.create(
        user=None,
        tier=monthly_tier,
        status='active',
        duration_type='monthly',
        start_date=now,
        end_date=now + timezone.timedelta(days=30),
        payment_method='telebirr',
        telebirr_phone_number='251911002200',
        auto_renew=False,
    )
    token = subscription.generate_subscription_token()
    try:
        response = _post_encrypted(
            '/subscription/validate-token/',
            {'token': token},
            server_public_key=_server_keys,
            client_keys=client_keys,
            view=validate_subscription_token,
        )

        assert response.status_code == 200
        assert response.data['phone'] == '251911002200'
    finally:
        subscription.delete()


def test_validate_subscription_token_rejects_unknown_token(db, _server_keys, client_keys):
    response = _post_encrypted(
        '/subscription/validate-token/',
        {'token': 'not-a-real-token'},
        server_public_key=_server_keys,
        client_keys=client_keys,
        view=validate_subscription_token,
    )

    assert response.status_code == 400


# ── "Set New PIN" actually sets it ──────────────────────────────────────────
#
# The screen a returning SuperApp subscriber lands on says "Verify & Set Your
# PIN", with a "Set New PIN" field. It was answering "Invalid password" to
# anyone who did exactly that: the endpoint compared the new PIN against the
# account's existing one, so the only way through was to remember the PIN the
# screen had just invited them to replace.
#
# What authorises the change is the SMS code -- sent to the number on this
# subscription, single-use, and now time-limited. The same proof every
# password reset runs on.


def _subscription_with_otp(
    user, tier, *, otp='123456', expires_in_minutes=30, phone='251988990011'
):
    now = timezone.now()
    return SubscriptionPlan.objects.create(
        user=user,
        tier=tier,
        status='active',
        duration_type='monthly',
        start_date=now,
        end_date=now + timezone.timedelta(days=30),
        payment_method='telebirr',
        telebirr_phone_number=phone,
        setup_otp=otp,
        setup_otp_expires_at=(
            now + timezone.timedelta(minutes=expires_in_minutes)
            if expires_in_minutes is not None
            else None
        ),
        auto_renew=False,
    )


def _set_pin(pin, *, server_keys, client_keys, otp='123456'):
    return _post_encrypted(
        '/auth/login-with-subscription-otp/',
        {'phone': '+251988990011', 'otp': otp, 'password': pin},
        server_public_key=server_keys,
        client_keys=client_keys,
        view=login_with_subscription_otp,
    )


def test_an_existing_pin_is_replaced_not_checked(db, monthly_tier, _server_keys, client_keys):
    """The reported bug, directly."""
    user = User.objects.create_user(username='has_a_pin', password='111111')
    subscription = _subscription_with_otp(user, monthly_tier)
    try:
        response = _set_pin('739284', server_keys=_server_keys, client_keys=client_keys)

        assert response.status_code == 200, response.data
        user.refresh_from_db()
        assert user.check_password('739284'), 'the new PIN was not set'
        assert not user.check_password('111111'), 'the old PIN still works'
    finally:
        subscription.delete()
        user.delete()


def test_the_new_pin_signs_them_in(db, monthly_tier, _server_keys, client_keys):
    user = User.objects.create_user(username='signs_in', password='111111')
    subscription = _subscription_with_otp(user, monthly_tier)
    try:
        response = _set_pin('739284', server_keys=_server_keys, client_keys=client_keys)

        assert response.data['token']
        assert response.data['user']['id'] == user.id
    finally:
        subscription.delete()
        user.delete()


def test_an_account_with_no_pin_still_gets_one(db, monthly_tier, _server_keys, client_keys):
    """The path that already worked must keep working."""
    user = User.objects.create_user(username='no_pin_yet', password=None)
    subscription = _subscription_with_otp(user, monthly_tier)
    try:
        response = _set_pin('739284', server_keys=_server_keys, client_keys=client_keys)

        assert response.status_code == 200, response.data
        user.refresh_from_db()
        assert user.check_password('739284')
    finally:
        subscription.delete()
        user.delete()


def test_the_code_is_spent_so_the_pin_cannot_be_set_twice(
    db, monthly_tier, _server_keys, client_keys
):
    """Otherwise the code is a standing reset token for that account."""
    user = User.objects.create_user(username='spent_code', password='111111')
    subscription = _subscription_with_otp(user, monthly_tier)
    try:
        _set_pin('739284', server_keys=_server_keys, client_keys=client_keys)
        subscription.refresh_from_db()
        assert subscription.setup_otp is None

        second = _set_pin('000999', server_keys=_server_keys, client_keys=client_keys)

        assert second.status_code == 400
        user.refresh_from_db()
        assert user.check_password('739284'), 'a spent code changed the PIN again'
    finally:
        subscription.delete()
        user.delete()


def test_an_expired_code_cannot_set_a_pin(db, monthly_tier, _server_keys, client_keys):
    """The 30-minute expiry was written by three paths and checked by none."""
    user = User.objects.create_user(username='expired_code', password='111111')
    subscription = _subscription_with_otp(user, monthly_tier, expires_in_minutes=-1)
    try:
        response = _set_pin('739284', server_keys=_server_keys, client_keys=client_keys)

        assert response.status_code == 400
        user.refresh_from_db()
        assert user.check_password('111111'), 'an expired code reset the PIN'
    finally:
        subscription.delete()
        user.delete()


def test_a_code_with_no_expiry_is_treated_as_expired(db, monthly_tier, _server_keys, client_keys):
    """Legacy rows. Resend issues a fresh one, so nobody is locked out."""
    user = User.objects.create_user(username='legacy_code', password='111111')
    subscription = _subscription_with_otp(user, monthly_tier, expires_in_minutes=None)
    try:
        response = _set_pin('739284', server_keys=_server_keys, client_keys=client_keys)

        assert response.status_code == 400
        user.refresh_from_db()
        assert user.check_password('111111')
    finally:
        subscription.delete()
        user.delete()


def test_a_wrong_code_cannot_set_a_pin(db, monthly_tier, _server_keys, client_keys):
    user = User.objects.create_user(username='wrong_code', password='111111')
    subscription = _subscription_with_otp(user, monthly_tier)
    try:
        response = _set_pin(
            '739284', server_keys=_server_keys, client_keys=client_keys, otp='999999'
        )

        assert response.status_code == 400
        user.refresh_from_db()
        assert user.check_password('111111')
    finally:
        subscription.delete()
        user.delete()


def test_a_weak_pin_is_still_refused(db, monthly_tier, _server_keys, client_keys):
    """Setting a PIN does not bypass the strength rule."""
    user = User.objects.create_user(username='weak_pin', password='111111')
    subscription = _subscription_with_otp(user, monthly_tier)
    try:
        response = _set_pin('123456', server_keys=_server_keys, client_keys=client_keys)

        assert response.status_code == 400
        user.refresh_from_db()
        assert user.check_password('111111')
    finally:
        subscription.delete()
        user.delete()


def test_the_endpoint_is_rate_limited():
    """A six-digit code that sets a PIN must not be guessable at speed."""
    from api.views.core import login_with_subscription_otp as view

    scopes = {getattr(t, 'scope', None) for t in getattr(view.cls, 'throttle_classes', [])}

    assert 'otp_verify' in scopes, 'the PIN-setting endpoint has no throttle'


# ── after a USSD Push payment, the code has to fit the screen ───────────────
#
# The webhook sent an OTPService code: five minutes, in the cache, readable
# only by /auth/login-with-otp/. An existing subscriber is handed to "Verify &
# Set Your PIN", which reads subscription.setup_otp instead -- so the code
# they were sent could never have satisfied the screen they were sent to, and
# five minutes rarely outlived the SMS queue anyway. "OTP expired or not
# found", on a subscription they had just paid for.


def test_the_ussd_webhook_issues_the_code_the_set_pin_screen_reads(db, monthly_tier):
    """A durable setup_otp on the row, not a five-minute cache entry."""
    from unittest.mock import patch

    from api.views.subscription import _send_ussd_access_sms

    user = User.objects.create_user(username='ussd_access_user', password=None)
    now = timezone.now()
    plan = SubscriptionPlan.objects.create(
        user=user,
        tier=monthly_tier,
        status='active',
        duration_type='monthly',
        start_date=now,
        end_date=now + timezone.timedelta(days=30),
        payment_method='telebirr',
        telebirr_phone_number='251988990011',
        auto_renew=False,
    )
    payment = SubscriptionPayment.objects.create(
        subscription=plan,
        user=user,
        amount=monthly_tier.price_etb,
        currency='ETB',
        status='completed',
        payment_method='telebirr',
        duration_type='monthly',
        period_start=now,
        period_end=plan.end_date,
        onevas_transaction_id='OCID-ACCESS-1',
    )
    try:
        with patch('api.services.sms_subscription.send_subscription_sms') as send:
            _send_ussd_access_sms(payment, monthly_tier, '251988990011')

        plan.refresh_from_db()
        assert plan.setup_otp, 'no setup_otp was issued'
        assert plan.setup_otp_expires_at > timezone.now()
        # 30 minutes, not the cache service's five.
        assert (plan.setup_otp_expires_at - timezone.now()).total_seconds() > 20 * 60

        send.assert_called_once()
        message = send.call_args.args[1]
        assert plan.setup_otp in message, 'the SMS does not carry the code'
        assert 'subscription_tp=true' in message, 'the SMS does not carry the way in'
        assert 'existing_user=true' in message, 'an account holder was sent to registration'
    finally:
        payment.delete()
        plan.delete()
        user.delete()


def test_that_code_then_sets_the_pin(db, monthly_tier, _server_keys, client_keys):
    """End to end: the code the webhook issues works on the screen it links to."""
    from unittest.mock import patch

    from api.views.subscription import _send_ussd_access_sms

    user = User.objects.create_user(username='ussd_pin_user', password='111111')
    now = timezone.now()
    plan = SubscriptionPlan.objects.create(
        user=user,
        tier=monthly_tier,
        status='active',
        duration_type='monthly',
        start_date=now,
        end_date=now + timezone.timedelta(days=30),
        payment_method='telebirr',
        telebirr_phone_number='251988990011',
        auto_renew=False,
    )
    payment = SubscriptionPayment.objects.create(
        subscription=plan,
        user=user,
        amount=monthly_tier.price_etb,
        currency='ETB',
        status='completed',
        payment_method='telebirr',
        duration_type='monthly',
        period_start=now,
        period_end=plan.end_date,
        onevas_transaction_id='OCID-ACCESS-2',
    )
    try:
        with patch('api.services.sms_subscription.send_subscription_sms'):
            _send_ussd_access_sms(payment, monthly_tier, '251988990011')
        plan.refresh_from_db()

        response = _post_encrypted(
            '/auth/login-with-subscription-otp/',
            {'phone': '+251988990011', 'otp': plan.setup_otp, 'password': '739284'},
            server_public_key=_server_keys,
            client_keys=client_keys,
            view=login_with_subscription_otp,
        )

        assert response.status_code == 200, response.data
        user.refresh_from_db()
        assert user.check_password('739284'), 'the PIN was not set'
    finally:
        payment.delete()
        plan.delete()
        user.delete()


# ── the web flow's first screen actually saves what it asks for ────────────
#
# The page collects a username and a PIN, validates both, and used to send
# neither. A subscriber chose credentials, paid, and arrived at a login that
# had never heard of them. Now they are written before the push, so the screen
# after payment can be an ordinary login.
#
# Safe on an AllowAny endpoint only because the verification session is
# consumed first: that proves the caller holds the number. Without it, a
# posted phone and PIN would be an account takeover, so the tests below pin
# that a push with no verification writes nothing at all.


def _initiate(tier, phone, *, client_public, username=None, pin=None, session=None):
    from rest_framework.test import APIClient

    from common.security.e2e_encryption import encrypt_payload

    body = {'tier_id': str(tier.id), 'phone_number': phone}
    if session is not None:
        body['verification_session_id'] = str(session)
    if username is not None:
        body['username'] = username
    if pin is not None:
        body['pin'] = pin

    server_public, client_pub, client_private = client_public
    sealed = encrypt_payload(body, server_public, client_private)
    api = APIClient()
    return api.post(
        '/api/v1/subscription/telebirr/ussd/initiate/',
        sealed.to_dict(),
        format='json',
        HTTP_X_CLIENT_PUBLIC_KEY=client_pub,
    )


@pytest.fixture
def _accepted_push():
    from unittest.mock import patch

    with patch('api.views.subscription.telebirr_direct_debit_service') as service:
        service.initiate_ussd_push_payment.return_value = {
            'success': True,
            'originator_conversation_id': 'OCID-ACC-1',
            'response_code': '0',
            'message': 'accepted',
        }
        yield service


def test_a_new_subscriber_gets_the_account_they_asked_for(
    db, monthly_tier, encrypted_client_keys, _accepted_push
):
    from tests.conftest import verified_push_session

    phone = '251988770011'
    session = verified_push_session(phone_number=phone, tier_id=str(monthly_tier.id))

    response = _initiate(
        monthly_tier,
        phone,
        client_public=encrypted_client_keys,
        username='chosen_name',
        pin='739284',
        session=session.id,
    )

    assert response.status_code == 200, response.data
    user = User.objects.get(username='chosen_name')
    assert user.check_password('739284')
    assert user.profile.phone_number == phone


def test_an_existing_subscriber_has_both_updated(
    db, monthly_tier, encrypted_client_keys, _accepted_push
):
    """The reported bug: already having an account meant neither was applied."""
    from tests.conftest import verified_push_session

    phone = '251988770022'
    user = User.objects.create_user(username='old_name', password='111111')
    user.profile.phone_number = phone
    user.profile.save(update_fields=['phone_number'])
    session = verified_push_session(phone_number=phone, tier_id=str(monthly_tier.id))

    response = _initiate(
        monthly_tier,
        phone,
        client_public=encrypted_client_keys,
        username='new_name',
        pin='739284',
        session=session.id,
    )

    assert response.status_code == 200, response.data
    user.refresh_from_db()
    assert user.username == 'new_name'
    assert user.check_password('739284')
    assert not user.check_password('111111')


def test_the_account_exists_before_the_push_is_sent(
    db, monthly_tier, encrypted_client_keys, _accepted_push
):
    """So a payment that never completes still leaves a usable login."""
    from tests.conftest import verified_push_session

    phone = '251988770033'
    session = verified_push_session(phone_number=phone, tier_id=str(monthly_tier.id))

    _accepted_push.initiate_ussd_push_payment.side_effect = (
        lambda **kwargs: AssertionError('push sent before the account was written')
        if not User.objects.filter(username='before_push').exists()
        else {'success': True, 'originator_conversation_id': 'OCID-ACC-2', 'response_code': '0'}
    )

    response = _initiate(
        monthly_tier,
        phone,
        client_public=encrypted_client_keys,
        username='before_push',
        pin='739284',
        session=session.id,
    )

    assert response.status_code == 200, response.data
    assert User.objects.filter(username='before_push').exists()


def test_a_taken_username_is_refused_and_nothing_is_charged(
    db, monthly_tier, encrypted_client_keys, _accepted_push
):
    from tests.conftest import verified_push_session

    User.objects.create_user(username='already_mine', password='x')
    phone = '251988770044'
    session = verified_push_session(phone_number=phone, tier_id=str(monthly_tier.id))

    response = _initiate(
        monthly_tier,
        phone,
        client_public=encrypted_client_keys,
        username='already_mine',
        pin='739284',
        session=session.id,
    )

    assert response.status_code == 409
    assert response.data['code'] == 'USERNAME_TAKEN'
    _accepted_push.initiate_ussd_push_payment.assert_not_called()
    # And the verification survives, so retrying costs no extra SMS.
    session.refresh_from_db()
    assert session.status == 'verified'


def test_a_weak_pin_is_refused_before_anything_happens(
    db, monthly_tier, encrypted_client_keys, _accepted_push
):
    from tests.conftest import verified_push_session

    phone = '251988770055'
    session = verified_push_session(phone_number=phone, tier_id=str(monthly_tier.id))

    response = _initiate(
        monthly_tier,
        phone,
        client_public=encrypted_client_keys,
        username='weak_pin_user',
        pin='123456',
        session=session.id,
    )

    assert response.status_code == 400
    assert not User.objects.filter(username='weak_pin_user').exists()
    _accepted_push.initiate_ussd_push_payment.assert_not_called()


def test_credentials_without_a_verified_number_write_nothing(
    db, monthly_tier, encrypted_client_keys, _accepted_push
):
    """The guard that makes this safe on an AllowAny endpoint."""
    phone = '251988770066'

    response = _initiate(
        monthly_tier,
        phone,
        client_public=encrypted_client_keys,
        username='no_proof',
        pin='739284',
    )

    assert response.status_code == 403
    assert not User.objects.filter(username='no_proof').exists()
    _accepted_push.initiate_ussd_push_payment.assert_not_called()


def test_a_flow_that_sends_no_credentials_is_unchanged(
    db, monthly_tier, encrypted_client_keys, _accepted_push
):
    """The SuperApp sends neither, and must keep working exactly as before."""
    from tests.conftest import verified_push_session

    phone = '251988770077'
    session = verified_push_session(phone_number=phone, tier_id=str(monthly_tier.id))

    response = _initiate(
        monthly_tier, phone, client_public=encrypted_client_keys, session=session.id
    )

    assert response.status_code == 200, response.data
    _accepted_push.initiate_ussd_push_payment.assert_called_once()


# ── a paid subscription must belong to somebody ─────────────────────────────
#
# Five active subscriptions on staging had user=None: paid for, activated, and
# owned by nobody. active_subscription_for() filters on user, so the person
# who paid was shown the subscribe page on their own profile.
#
# The cause was an entry point, not the logic. _activate_ussd_subscription_
# payment is the only place a USSD subscription activates, but it is reached
# from two places: the subscription webhook, which resolved the owner from the
# payment metadata first, and api/views/wallet.py's coin webhook, which called
# straight through. Telebirr registers ONE Result Address per merchant and
# sends every confirmation to the coin one -- so the resolving path never ran.


def _pending_ussd_payment(tier, phone, *, txn='S_X-ORPHAN-1'):
    """A plan and payment exactly as an anonymous web subscriber leaves them."""
    now = timezone.now()
    plan = SubscriptionPlan.objects.create(
        user=None,
        tier=tier,
        status='pending',
        duration_type='monthly',
        start_date=now,
        end_date=now + timezone.timedelta(days=30),
        payment_method='telebirr',
        auto_renew=False,
    )
    payment = SubscriptionPayment.objects.create(
        subscription=plan,
        user=None,
        amount=tier.price_etb,
        currency='ETB',
        status='pending',
        payment_method='telebirr',
        duration_type='monthly',
        period_start=now,
        period_end=plan.end_date,
        onevas_transaction_id=txn,
        metadata={'phone_number': phone},
    )
    return plan, payment


def test_activation_through_the_coin_webhook_still_finds_the_owner(db, monthly_tier):
    """The path Telebirr actually uses."""
    from api.views.subscription import _activate_ussd_subscription_payment

    phone = '251911528271'
    user = User.objects.create_user(username='orphan_owner', password='x')
    user.profile.phone_number = phone
    user.profile.save(update_fields=['phone_number'])
    plan, payment = _pending_ussd_payment(monthly_tier, phone)

    _activate_ussd_subscription_payment(payment, monthly_tier)

    plan.refresh_from_db()
    payment.refresh_from_db()
    assert plan.user_id == user.id, 'the activated plan belongs to nobody'
    assert payment.user_id == user.id
    assert plan.status == 'active'


def test_the_subscriber_can_then_see_their_own_subscription(db, monthly_tier):
    """The symptom: the paywall on your own profile after paying."""
    from api.services.subscription_access import active_subscription_for
    from api.views.subscription import _activate_ussd_subscription_payment

    phone = '251911528272'
    user = User.objects.create_user(username='sees_own_sub', password='x')
    user.profile.phone_number = phone
    user.profile.save(update_fields=['phone_number'])
    plan, payment = _pending_ussd_payment(monthly_tier, phone, txn='S_X-ORPHAN-2')

    assert active_subscription_for(user=user) is None

    _activate_ussd_subscription_payment(payment, monthly_tier)

    assert active_subscription_for(user=user) is not None


def test_an_account_is_created_when_the_number_is_new(db, monthly_tier):
    """A first-time subscriber has no profile to find."""
    from api.views.subscription import _activate_ussd_subscription_payment

    phone = '251911528273'
    plan, payment = _pending_ussd_payment(monthly_tier, phone, txn='S_X-ORPHAN-3')

    _activate_ussd_subscription_payment(payment, monthly_tier)

    plan.refresh_from_db()
    assert plan.user is not None
    assert plan.user.profile.phone_number == phone
    assert payment.metadata.get('is_new_user') is True


def test_the_activated_plan_records_the_phone_number(db, monthly_tier):
    """Both columns were null, so an orphan could not be matched back by hand."""
    from api.views.subscription import _activate_ussd_subscription_payment

    phone = '251911528274'
    plan, payment = _pending_ussd_payment(monthly_tier, phone, txn='S_X-ORPHAN-4')

    _activate_ussd_subscription_payment(payment, monthly_tier)

    plan.refresh_from_db()
    assert plan.telebirr_phone_number == phone


def test_a_payment_with_no_number_activates_as_before(db, monthly_tier):
    """No number to resolve from is not an error -- behaviour is unchanged."""
    from api.views.subscription import _activate_ussd_subscription_payment

    plan, payment = _pending_ussd_payment(monthly_tier, '251911528275', txn='S_X-ORPHAN-5')
    SubscriptionPayment.objects.filter(pk=payment.pk).update(metadata={})
    payment.refresh_from_db()

    _activate_ussd_subscription_payment(payment, monthly_tier)

    plan.refresh_from_db()
    assert plan.status == 'active'
    assert plan.user is None
