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
from tests.conftest import verified_push_session

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

    body = {
        'tier_id': str(tier_id),
        # Every push now needs one. A test that omitted it would be refused
        # before reaching the behaviour it is about.
        'verification_session_id': str(
            verified_push_session(
                purpose='subscription',
                phone_number=phone_number,
                user=user,
                tier_id=str(tier_id),
            ).id
        ),
    }
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
        # Unique per call: the view stores this as onevas_transaction_id, which
        # is unique, so a constant would collide the moment a test legitimately
        # initiates twice.
        return {
            'success': True,
            'originator_conversation_id': f'TEST-CONV-{len(sent)}',
        }

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


# ─── the gap ALREADY_SUBSCRIBED cannot see ────────────────────────────────────
#
# A payment whose callback never lands leaves the subscription *pending*, so
# the caller still looks like a non-subscriber: the active-subscription guard
# does not fire and they can be charged again. This is the live UAT failure --
# nothing has listened on the telebirr result port since the cluster rebuild,
# so every USSD confirmation is lost and every subscription stays pending.


@pytest.fixture
def fresh_caller(db, tier):
    """Someone with no subscription at all -- the state a lost callback leaves."""
    u = User.objects.create_user(username='pending_user', password='x')
    u.profile.phone_number = '251911222333'
    u.profile.save()
    yield u
    u.delete()


def test_a_lost_callback_leaves_no_active_subscription_to_guard_on(fresh_caller):
    """Establishes why a second guard is needed at all."""
    from api.services.subscription_access import pending_subscription_payment

    assert active_subscription_for(user=fresh_caller) is None
    assert pending_subscription_payment(user=fresh_caller) is None


def test_a_second_tap_is_refused_while_the_first_is_unconfirmed(
    fresh_caller, tier, encrypted_client_keys, no_real_payments
):
    first = call_initiate(encrypted_client_keys, tier.id, user=fresh_caller)
    assert first.status_code != 409, first.content
    assert len(no_real_payments) == 1, 'the first attempt should go through'

    second = call_initiate(encrypted_client_keys, tier.id, user=fresh_caller)

    assert second.status_code == 409, second.content
    # The charge that would have been duplicated never happened.
    assert len(no_real_payments) == 1


def test_repeated_taps_charge_exactly_once(
    fresh_caller, tier, encrypted_client_keys, no_real_payments
):
    for _ in range(6):
        call_initiate(encrypted_client_keys, tier.id, user=fresh_caller)

    assert len(no_real_payments) == 1


def test_an_unauthenticated_repeat_is_refused_by_phone(
    db, tier, encrypted_client_keys, no_real_payments
):
    """The SuperApp flow, where the pending payment carries only a phone."""
    phone = '251955666777'
    call_initiate(encrypted_client_keys, tier.id, phone_number=phone)
    assert len(no_real_payments) == 1

    again = call_initiate(encrypted_client_keys, tier.id, phone_number=phone)

    assert again.status_code == 409, again.content
    assert len(no_real_payments) == 1


def test_a_different_caller_is_unaffected(
    fresh_caller, tier, encrypted_client_keys, no_real_payments
):
    call_initiate(encrypted_client_keys, tier.id, user=fresh_caller)
    call_initiate(encrypted_client_keys, tier.id, phone_number='251977888999')

    assert len(no_real_payments) == 2


def test_the_block_expires_so_a_lost_callback_is_not_a_permanent_lockout(
    fresh_caller, tier, encrypted_client_keys, no_real_payments
):
    """A confirmation that never arrives must not bar them from ever subscribing."""
    from api.models.subscription import SubscriptionPayment
    from api.services.subscription_access import PENDING_PAYMENT_WINDOW_SECONDS

    call_initiate(encrypted_client_keys, tier.id, user=fresh_caller)
    assert len(no_real_payments) == 1

    # Age the pending payment past the window.
    SubscriptionPayment.objects.filter(status='pending').update(
        created_at=timezone.now() - timedelta(seconds=PENDING_PAYMENT_WINDOW_SECONDS + 60)
    )

    later = call_initiate(encrypted_client_keys, tier.id, user=fresh_caller)

    assert later.status_code != 409, later.content
    assert len(no_real_payments) == 2


def test_the_refusal_says_it_is_confirming_not_that_it_failed(
    fresh_caller, tier, encrypted_client_keys, no_real_payments
):
    """Telling them it failed is what invites the duplicate charge."""
    from api.services.subscription_access import payment_pending_payload

    call_initiate(encrypted_client_keys, tier.id, user=fresh_caller)
    payload = payment_pending_payload()

    assert payload['code'] == 'PAYMENT_PENDING'
    assert 'confirm' in payload['error'].lower()
