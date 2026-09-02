"""
Subscribing twice must not charge twice.

The page hides the plan chooser once it knows a subscription is active, but it
cannot always know: in the telebirr SuperApp the visitor is unauthenticated,
``/subscriptions/`` 401s for them, and the chooser is all they ever see. So the
refusal has to live on the server, before the USSD push is sent -- and it has
to resolve the caller by phone number, which is the only identity that flow
has before the OTP login that follows payment.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from api.models.subscription import SubscriptionPlan, SubscriptionTier
from api.services.subscription_access import (
    ALREADY_SUBSCRIBED_CODE,
    active_subscription_for,
    already_subscribed_payload,
    subscription_summary,
)

pytestmark = pytest.mark.integration

PHONE = '251944365493'


@pytest.fixture
def tier(db):
    t = SubscriptionTier.objects.create(
        name='Weekly Premium',
        slug='weekly-premium',
        price_etb=Decimal('20.00'),
        duration_type='weekly',
        duration_days=7,
        is_active=True,
    )
    yield t
    t.delete()


@pytest.fixture
def subscriber(db, tier):
    u = User.objects.create_user(username='dupe_user', password='x')
    u.profile.phone_number = PHONE
    u.profile.save()
    now = timezone.now()
    SubscriptionPlan.objects.create(
        user=u,
        tier=tier,
        status='active',
        duration_type='weekly',
        start_date=now,
        end_date=now + timedelta(days=7),
    )
    yield u
    u.delete()


# ─── resolving the caller ─────────────────────────────────────────────────────


def test_an_authenticated_subscriber_is_found(subscriber):
    assert active_subscription_for(user=subscriber) is not None


def test_an_unauthenticated_caller_is_found_by_phone(subscriber):
    """The SuperApp case: no session, only a phone number."""
    assert active_subscription_for(user=None, phone_number=PHONE) is not None


def test_an_unknown_phone_has_no_subscription(db, tier):
    assert active_subscription_for(user=None, phone_number='251900000000') is None


def test_no_identity_at_all_yields_nothing(db):
    assert active_subscription_for() is None


# ─── what counts as active ────────────────────────────────────────────────────


def test_an_expired_plan_does_not_block_resubscribing(subscriber):
    """A lapsed subscriber must be able to buy again."""
    plan = SubscriptionPlan.objects.get(user=subscriber)
    plan.end_date = timezone.now() - timedelta(seconds=1)
    plan.save()

    assert active_subscription_for(user=subscriber) is None


def test_a_cancelled_plan_does_not_block_resubscribing(subscriber):
    plan = SubscriptionPlan.objects.get(user=subscriber)
    plan.status = 'cancelled'
    plan.save()

    assert active_subscription_for(user=subscriber) is None


def test_a_plan_with_no_end_date_still_counts_as_active(subscriber):
    """Open-ended plans have a null end_date; they must not be treated as expired."""
    plan = SubscriptionPlan.objects.get(user=subscriber)
    plan.end_date = None
    plan.save()

    assert active_subscription_for(user=subscriber) is not None


# ─── the refusal the client branches on ───────────────────────────────────────


def test_the_refusal_names_the_plan_they_already_have(subscriber):
    plan = active_subscription_for(user=subscriber)
    payload = already_subscribed_payload(plan)

    assert payload['success'] is False
    assert payload['code'] == ALREADY_SUBSCRIBED_CODE
    assert payload['subscription']['tier_name'] == 'Weekly Premium'
    assert payload['subscription']['end_date'] is not None


def test_the_summary_carries_no_account_identifiers(subscriber):
    """It is returned to an unauthenticated caller, so it must not leak."""
    summary = subscription_summary(active_subscription_for(user=subscriber))

    assert set(summary) == {'tier_name', 'duration_type', 'start_date', 'end_date'}
    serialised = str(summary)
    assert 'dupe_user' not in serialised
    assert PHONE not in serialised


# ─── the endpoint: no second charge ───────────────────────────────────────────


def call_initiate(client_public, tier_id, phone_number=None, user=None):
    """Drive the real endpoint through the E2E transport, as a client does."""
    from rest_framework.test import APIClient

    from common.security.e2e_encryption import encrypt_payload

    body = {'tier_id': str(tier_id)}
    if phone_number:
        body['phone_number'] = phone_number

    server_public, client_pub, client_private = client_public
    sealed = encrypt_payload(body, server_public, client_private)

    api = APIClient()
    if user is not None:
        api.force_authenticate(user=user)
    return api.post(
        '/api/v1/subscription/telebirr/ussd/initiate/',
        sealed.to_dict(),
        format='json',
        HTTP_X_CLIENT_PUBLIC_KEY=client_pub,
    )


@pytest.fixture
def no_real_payments(monkeypatch):
    """Records whether a USSD push would have been sent."""
    from api.views import subscription as subscription_views

    sent = []

    def _spy(**kwargs):
        sent.append(kwargs)
        return {'success': True, 'originator_conversation_id': 'SHOULD-NOT-HAPPEN'}

    monkeypatch.setattr(
        subscription_views.telebirr_direct_debit_service,
        'initiate_ussd_push_payment',
        _spy,
    )
    return sent


def test_an_active_subscriber_is_refused_before_any_charge(
    subscriber, tier, encrypted_client_keys, no_real_payments
):
    response = call_initiate(encrypted_client_keys, tier.id, user=subscriber)

    assert response.status_code == 409, response.content
    # The whole point: no USSD push was sent, so nothing was charged.
    assert no_real_payments == []


def test_an_unauthenticated_subscriber_is_refused_by_phone(
    subscriber, tier, encrypted_client_keys, no_real_payments
):
    """The SuperApp case the client-side check cannot cover."""
    response = call_initiate(encrypted_client_keys, tier.id, phone_number=PHONE)

    assert response.status_code == 409, response.content
    assert no_real_payments == []


def test_repeated_attempts_never_charge(subscriber, tier, encrypted_client_keys, no_real_payments):
    for _ in range(5):
        call_initiate(encrypted_client_keys, tier.id, phone_number=PHONE)
    assert no_real_payments == []


def test_a_non_subscriber_is_still_allowed_through(
    db, tier, encrypted_client_keys, no_real_payments
):
    """The guard must not block a genuine first subscription."""
    response = call_initiate(encrypted_client_keys, tier.id, phone_number='251911111111')

    assert response.status_code != 409, response.content
    assert len(no_real_payments) == 1
