"""
Regression tests for resend_subscription_otp (api/views/core.py) -- ported
from the master branch, missing entirely in the current project before this
change. Companion to login_with_subscription_otp: lets a customer with an
active subscription get a fresh setup_otp via SMS without re-subscribing.

Always responds with a generic success message regardless of whether a
matching subscription exists, to avoid phone enumeration -- only the
DEBUG-only `dev_code` field and (indirectly) the SMS side effect reveal
whether a real OTP was issued.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from api.models.subscription import SubscriptionPlan, SubscriptionTier
from api.services.sms.dispatch import SmsNotQueued
from api.views.core import resend_subscription_otp

pytestmark = pytest.mark.integration

factory = APIRequestFactory()

# The OTP goes straight onto the TIMWE SMS queue. It used to go through
# OnevasWebhookView.send_sms; OneVAS, and that view, have been removed.
QUEUE_SMS = 'api.services.sms.dispatch.queue_sms'


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def active_subscription(db):
    tier = SubscriptionTier.objects.create(
        name='Resend OTP Test Daily',
        slug='resend-otp-test-daily',
        duration_type='daily',
        duration_days=1,
        price_etb=10,
        onevas_code='R1',
        spid='rsp1',
        service_id='rsvc1',
        product_id='rprod1',
    )
    plan = SubscriptionPlan.objects.create(
        tier=tier,
        status='active',
        payment_method='timwe',
        onevas_phone_number='251911000111',
        start_date=timezone.now(),
        end_date=timezone.now() + timezone.timedelta(days=1),
        setup_otp='111111',
        setup_otp_expires_at=timezone.now() + timezone.timedelta(minutes=5),
    )
    yield plan
    plan.delete()
    tier.delete()


def test_resend_subscription_otp_regenerates_otp_and_sends_sms(active_subscription):
    with patch(QUEUE_SMS) as mock_send:
        request = factory.post(
            '/auth/resend-subscription-otp/', {'phone': '0911000111'}, format='json'
        )

        response = resend_subscription_otp(request)

    assert response.status_code == 200, response.data
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs['phone_number'] == '251911000111'
    assert mock_send.call_args.kwargs['purpose'] == 'otp_subscription_resend'
    active_subscription.refresh_from_db()
    assert active_subscription.setup_otp is not None
    assert active_subscription.setup_otp != '111111'
    assert active_subscription.setup_otp in mock_send.call_args.kwargs['text']


def test_resend_subscription_otp_makes_no_http_call(active_subscription, monkeypatch):
    """The OTP leaves only through the TIMWE SMPP queue -- never an HTTP gateway."""
    posted = []
    monkeypatch.setattr('requests.post', lambda *a, **kw: posted.append((a, kw)))

    with patch(QUEUE_SMS) as queued:
        resend_subscription_otp(
            factory.post('/auth/resend-subscription-otp/', {'phone': '0911000111'}, format='json'),
        )

    queued.assert_called_once()
    assert posted == []


def test_resend_subscription_otp_sets_cooldown(active_subscription):
    with patch(QUEUE_SMS):
        resend_subscription_otp(
            factory.post('/auth/resend-subscription-otp/', {'phone': '0911000111'}, format='json')
        )

    with patch(QUEUE_SMS) as mock_send:
        response = resend_subscription_otp(
            factory.post('/auth/resend-subscription-otp/', {'phone': '0911000111'}, format='json'),
        )

    assert response.status_code == 429
    assert not mock_send.called


def test_resend_subscription_otp_returns_502_when_sms_cannot_be_queued(active_subscription):
    with patch(QUEUE_SMS, side_effect=SmsNotQueued('unusable number')):
        response = resend_subscription_otp(
            factory.post('/auth/resend-subscription-otp/', {'phone': '0911000111'}, format='json'),
        )

    assert response.status_code == 502


def test_resend_subscription_otp_returns_generic_success_for_unknown_phone(db):
    """No matching subscription -- still 200 with the generic message, to
    avoid revealing whether a phone number has a subscription."""
    request = factory.post('/auth/resend-subscription-otp/', {'phone': '0999888777'}, format='json')

    response = resend_subscription_otp(request)

    assert response.status_code == 200
    assert 'if an active subscription exists' in response.data['message'].lower()


def test_resend_subscription_otp_rejects_invalid_phone(db):
    request = factory.post(
        '/auth/resend-subscription-otp/', {'phone': 'not-a-phone'}, format='json'
    )

    response = resend_subscription_otp(request)

    assert response.status_code == 400


def test_resend_subscription_otp_rejects_missing_phone(db):
    request = factory.post('/auth/resend-subscription-otp/', {}, format='json')

    response = resend_subscription_otp(request)

    assert response.status_code == 400
