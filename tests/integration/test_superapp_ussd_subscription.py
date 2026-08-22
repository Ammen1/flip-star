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

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from api.models.subscription import SubscriptionPayment, SubscriptionPlan, SubscriptionTier
from api.views.subscription import (
    check_superapp_subscription,
    telebirr_ussd_subscription_initiate,
    telebirr_ussd_subscription_status,
    telebirr_ussd_subscription_webhook,
    validate_subscription_token,
)

pytestmark = pytest.mark.integration

factory = APIRequestFactory()
plain_factory = RequestFactory()


@pytest.fixture
def monthly_tier(db):
    tier = SubscriptionTier.objects.create(
        name='USSD Test Monthly', slug='ussd-test-monthly', duration_type='monthly', duration_days=30,
        price_etb=150, onevas_code='U1', spid='sp', service_id='svc', product_id='prod', is_active=True,
    )
    yield tier
    tier.delete()


def _soap_result(*, originator_conversation_id, result_code, transaction_id='', result_desc=''):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
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
</soapenv:Envelope>'''.encode()


# ---------------------------------------------------------------------------
# telebirr_ussd_subscription_initiate: never activates directly
# ---------------------------------------------------------------------------

def test_initiate_creates_pending_subscription_not_active(db, monthly_tier):
    with patch(
        'api.views.subscription.telebirr_direct_debit_service.initiate_ussd_push_payment',
        return_value={'success': True, 'originator_conversation_id': 'S_X_USSD1', 'conversation_id': 'AG_USSD1'},
    ):
        request = factory.post('/subscription/telebirr/ussd/initiate/', {
            'tier_id': str(monthly_tier.id), 'phone_number': '0911223344',
        }, format='json')

        response = telebirr_ussd_subscription_initiate(request)

    assert response.status_code == 200, response.data
    payment = SubscriptionPayment.objects.get(onevas_transaction_id='S_X_USSD1')
    assert payment.status == 'pending'
    assert payment.subscription.status == 'pending'
    assert payment.subscription.status != 'active'


def test_initiate_requires_phone_for_anonymous_user(db, monthly_tier):
    request = factory.post('/subscription/telebirr/ussd/initiate/', {'tier_id': str(monthly_tier.id)}, format='json')

    response = telebirr_ussd_subscription_initiate(request)

    assert response.status_code == 400


def test_initiate_rejects_unknown_tier(db):
    request = factory.post('/subscription/telebirr/ussd/initiate/', {
        'tier_id': '00000000-0000-0000-0000-000000000000', 'phone_number': '0911223344',
    }, format='json')

    response = telebirr_ussd_subscription_initiate(request)

    assert response.status_code == 404


def test_initiate_returns_error_when_telebirr_call_fails(db, monthly_tier):
    with patch(
        'api.views.subscription.telebirr_direct_debit_service.initiate_ussd_push_payment',
        return_value={'success': False, 'error': 'upstream down'},
    ):
        request = factory.post('/subscription/telebirr/ussd/initiate/', {
            'tier_id': str(monthly_tier.id), 'phone_number': '0911223344',
        }, format='json')

        response = telebirr_ussd_subscription_initiate(request)

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
        user=None, tier=monthly_tier, status='pending', duration_type='monthly',
        start_date=start, end_date=end, payment_method='telebirr', auto_renew=False,
    )
    payment = SubscriptionPayment.objects.create(
        user=None, subscription=subscription, amount=monthly_tier.price_etb, currency='ETB',
        status='pending', payment_method='telebirr', onevas_transaction_id='S_X_USSDWEBHOOK1',
        duration_type='monthly', period_start=start, period_end=end,
        metadata={'phone_number': '251966778899'},
    )
    yield payment
    payment.delete()
    subscription.delete()


def test_webhook_activates_pending_subscription_and_creates_user(pending_ussd_payment):
    body = _soap_result(originator_conversation_id='S_X_USSDWEBHOOK1', result_code='0', transaction_id='TXNUSSD1')
    request = plain_factory.post('/webhooks/telebirrSubscriptionUssd/', data=body, content_type='text/xml')

    with patch('api.services.otp.OTPService.send_otp', return_value=(True, 'ok')):
        response = telebirr_ussd_subscription_webhook(request)

    assert response.status_code == 200

    pending_ussd_payment.refresh_from_db()
    assert pending_ussd_payment.status == 'completed'
    assert pending_ussd_payment.subscription.status == 'active'
    assert pending_ussd_payment.user is not None
    assert pending_ussd_payment.user.profile.phone_number == '251966778899'


def test_webhook_marks_payment_failed_on_telebirr_failure(pending_ussd_payment):
    body = _soap_result(originator_conversation_id='S_X_USSDWEBHOOK1', result_code='1', result_desc='declined')
    request = plain_factory.post('/webhooks/telebirrSubscriptionUssd/', data=body, content_type='text/xml')

    response = telebirr_ussd_subscription_webhook(request)

    assert response.status_code == 200
    pending_ussd_payment.refresh_from_db()
    assert pending_ussd_payment.status == 'failed'
    assert pending_ussd_payment.subscription.status == 'pending'
    assert pending_ussd_payment.subscription.status != 'active'


def test_webhook_duplicate_delivery_does_not_double_activate(pending_ussd_payment):
    body = _soap_result(originator_conversation_id='S_X_USSDWEBHOOK1', result_code='0', transaction_id='TXNUSSD2')

    with patch('api.services.otp.OTPService.send_otp', return_value=(True, 'ok')):
        telebirr_ussd_subscription_webhook(plain_factory.post('/webhooks/telebirrSubscriptionUssd/', data=body, content_type='text/xml'))
        first_user_id = SubscriptionPayment.objects.get(pk=pending_ussd_payment.pk).user_id

        telebirr_ussd_subscription_webhook(plain_factory.post('/webhooks/telebirrSubscriptionUssd/', data=body, content_type='text/xml'))

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
        user=None, tier=monthly_tier, status='pending', duration_type='monthly',
        start_date=start, end_date=end, payment_method='telebirr', auto_renew=False,
    )
    payment = SubscriptionPayment.objects.create(
        user=None, subscription=subscription, amount=monthly_tier.price_etb, currency='ETB',
        status='pending', payment_method='telebirr', onevas_transaction_id='S_X_USSDWEBHOOK2',
        duration_type='monthly', period_start=start, period_end=end,
        metadata={'phone_number': '251977889900'},
    )
    try:
        body = _soap_result(originator_conversation_id='S_X_USSDWEBHOOK2', result_code='0', transaction_id='TXNUSSD3')

        with patch('api.services.otp.OTPService.send_otp', return_value=(True, 'ok')):
            telebirr_ussd_subscription_webhook(plain_factory.post('/webhooks/telebirrSubscriptionUssd/', data=body, content_type='text/xml'))

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

def test_status_returns_found_false_for_unknown_id(db):
    request = plain_factory.get('/subscription/telebirr/ussd/status/?originator_conversation_id=nope')

    response = telebirr_ussd_subscription_status(request)

    assert response.status_code == 200
    assert response.data['found'] is False


def test_status_reflects_pending_payment(pending_ussd_payment):
    request = plain_factory.get(f'/subscription/telebirr/ussd/status/?originator_conversation_id={pending_ussd_payment.onevas_transaction_id}')

    response = telebirr_ussd_subscription_status(request)

    assert response.status_code == 200
    assert response.data['found'] is True
    assert response.data['status'] == 'pending'
    assert response.data['subscription_status'] == 'pending'


def test_status_requires_originator_conversation_id(db):
    request = plain_factory.get('/subscription/telebirr/ussd/status/')

    response = telebirr_ussd_subscription_status(request)

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# check_superapp_subscription / validate_subscription_token
# ---------------------------------------------------------------------------

def test_check_superapp_subscription_finds_active_telebirr_subscription(db, monthly_tier):
    now = timezone.now()
    subscription = SubscriptionPlan.objects.create(
        user=None, tier=monthly_tier, status='active', duration_type='monthly',
        start_date=now, end_date=now + timezone.timedelta(days=30), payment_method='telebirr',
        telebirr_phone_number='251988990011', auto_renew=False,
    )
    try:
        request = factory.post('/subscription/check-superapp/', {'phone': '0988990011'}, format='json')

        response = check_superapp_subscription(request)

        assert response.status_code == 200
        assert response.data['has_active_subscription'] is True
        assert response.data['user_exists'] is False
    finally:
        subscription.delete()


def test_check_superapp_subscription_no_match(db):
    request = factory.post('/subscription/check-superapp/', {'phone': '0900000000'}, format='json')

    response = check_superapp_subscription(request)

    assert response.status_code == 200
    assert response.data['has_active_subscription'] is False


def test_validate_subscription_token_returns_phone(db, monthly_tier):
    now = timezone.now()
    subscription = SubscriptionPlan.objects.create(
        user=None, tier=monthly_tier, status='active', duration_type='monthly',
        start_date=now, end_date=now + timezone.timedelta(days=30), payment_method='telebirr',
        telebirr_phone_number='251911002200', auto_renew=False,
    )
    token = subscription.generate_subscription_token()
    try:
        request = factory.post('/subscription/validate-token/', {'token': token}, format='json')

        response = validate_subscription_token(request)

        assert response.status_code == 200
        assert response.data['phone'] == '251911002200'
    finally:
        subscription.delete()


def test_validate_subscription_token_rejects_unknown_token(db):
    request = factory.post('/subscription/validate-token/', {'token': 'not-a-real-token'}, format='json')

    response = validate_subscription_token(request)

    assert response.status_code == 400
