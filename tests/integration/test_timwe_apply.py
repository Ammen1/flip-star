"""
Subscription changes applied from TIMWE syncOrderRelation notifications.

These cover api.views.timwe._apply_relation, which is the function the
integration flag gates. It stayed unimplemented while the OneVAS webhooks
owned the subscription lifecycle; these tests pin the behaviour it must have
before TIMWE_INTEGRATION_ENABLED can be turned on.

The cases that matter are the ones that are not "it worked": a retried
notification must not create a second subscription, a cancellation for
something already gone must not error, and a cancellation for Daily must not
touch Monthly.
"""

import pytest
from django.contrib.auth.models import User

from api.integrations.timwe.datasync import SyncOrderRelation
from api.models import (
    SubscriptionHistory,
    SubscriptionPlan,
    SubscriptionTier,
    TimweSyncOrderLog,
)
from api.views.timwe import _apply_relation

pytestmark = pytest.mark.django_db

MSISDN = '251912345678'


def _relation(update_type=1, product_id='P-DAILY', transaction_id='TX-1', msisdn=MSISDN):
    extensions = {}
    if transaction_id:
        extensions['transactionID'] = transaction_id
    extensions['orderKey'] = 'OK-1'
    return SyncOrderRelation(
        user_id=msisdn,
        user_type=0,
        sp_id='001100',
        product_id=product_id,
        service_id='0011002000001100',
        update_type=update_type,
        update_time='20260830120000',
        extensions=extensions,
    )


@pytest.fixture
def daily_tier():
    return SubscriptionTier.objects.create(
        name='Daily Premium',
        slug='daily-premium',
        duration_type='daily',
        duration_days=1,
        price_etb=5,
        product_id='P-DAILY',
        # slug and onevas_code are both unique; two tiers defaulting to ''
        # collide on insert.
        onevas_code='TDAILY',
    )


@pytest.fixture
def monthly_tier():
    return SubscriptionTier.objects.create(
        name='Monthly Premium',
        slug='monthly-premium',
        duration_type='monthly',
        duration_days=30,
        price_etb=100,
        product_id='P-MONTHLY',
        onevas_code='TMONTHLY',
    )


@pytest.fixture
def user():
    return User.objects.create_user(username='sub1', password='x')


# --------------------------------------------------------------------------
# Subscribe
# --------------------------------------------------------------------------


def test_subscribe_activates_a_plan(daily_tier, user):
    applied, description = _apply_relation(_relation(), daily_tier, user)

    assert applied is True
    # 'created' rather than 'activated': the description now distinguishes a
    # first subscription from a renewal, which is what reconciliation against
    # TIMWE's own records needs.
    assert description == 'Subscription created.'

    plan = SubscriptionPlan.objects.get(user=user, tier=daily_tier)
    assert plan.status == 'active'
    assert plan.start_date is not None
    # activate() derives this from tier.duration_days; a null end_date here
    # would mean the subscription never expires.
    assert plan.end_date is not None


def test_subscribe_without_a_known_user_keeps_the_msisdn(daily_tier):
    """SMS-first: the subscriber has no account yet, so the row carries none."""
    applied, _ = _apply_relation(_relation(), daily_tier, None)

    assert applied is True
    plan = SubscriptionPlan.objects.get(tier=daily_tier)
    assert plan.user is None
    assert plan.onevas_phone_number == MSISDN


def test_subscribe_records_history(daily_tier, user):
    _apply_relation(_relation(), daily_tier, user)

    entry = SubscriptionHistory.objects.get(user=user, action='created')
    assert entry.metadata['source'] == 'timwe'
    assert entry.metadata['transaction_id'] == 'TX-1'


def test_a_second_charge_renews_rather_than_duplicating(daily_tier, user):
    """
    A *new* transactionID on an active plan means the MA charged again.

    This used to answer 'Subscription already active' and do nothing, which
    meant a subscriber was billed for a period they never received. It now
    renews in place -- one plan, extended -- matching the OneVAS webhook.
    A retry of the *same* transactionID is still refused; that is the test
    below.
    """
    _apply_relation(_relation(), daily_tier, user)
    before = SubscriptionPlan.objects.get(user=user, tier=daily_tier).end_date

    applied, description = _apply_relation(_relation(transaction_id='TX-2'), daily_tier, user)

    assert applied is True
    assert description == 'Subscription renewed.'
    assert SubscriptionPlan.objects.filter(user=user, tier=daily_tier).count() == 1
    assert SubscriptionPlan.objects.get(user=user, tier=daily_tier).end_date >= before


def test_duplicate_transaction_id_is_not_applied_twice(daily_tier, user):
    """
    Idempotency on the MA's own event identifier.

    Distinct from the test above: that one is caught by the active-plan check,
    this one by transactionID -- which is what protects a *cancel* retried
    after the plan is already gone from being re-processed.
    """
    TimweSyncOrderLog.objects.create(
        event_type='subscription',
        update_type=1,
        msisdn=MSISDN,
        product_id='P-DAILY',
        transaction_id='TX-1',
        applied=True,
    )

    applied, description = _apply_relation(_relation(), daily_tier, user)

    assert applied is False
    assert 'duplicate' in description.lower()
    assert not SubscriptionPlan.objects.filter(user=user).exists()


# --------------------------------------------------------------------------
# Unsubscribe
# --------------------------------------------------------------------------


def test_unsubscribe_cancels_the_plan(daily_tier, user):
    _apply_relation(_relation(), daily_tier, user)

    applied, description = _apply_relation(
        _relation(update_type=2, transaction_id='TX-2'), daily_tier, user
    )

    assert applied is True
    assert description == 'Subscription cancelled.'

    plan = SubscriptionPlan.objects.get(user=user, tier=daily_tier)
    assert plan.status == 'cancelled'
    assert plan.cancelled_at is not None
    assert plan.auto_renew is False


def test_unsubscribe_with_nothing_active_is_not_an_error(daily_tier, user):
    """
    Answering 2031 here would make the MA retry a cancellation we can never
    satisfy. It is reporting something it has already done.
    """
    applied, description = _apply_relation(_relation(update_type=2), daily_tier, user)

    assert applied is False
    assert description == 'No active subscription to cancel.'


def test_unsubscribe_only_touches_the_named_tier(daily_tier, monthly_tier, user):
    _apply_relation(_relation(), daily_tier, user)
    _apply_relation(_relation(product_id='P-MONTHLY', transaction_id='TX-2'), monthly_tier, user)

    _apply_relation(_relation(update_type=2, transaction_id='TX-3'), daily_tier, user)

    assert SubscriptionPlan.objects.get(user=user, tier=daily_tier).status == 'cancelled'
    assert SubscriptionPlan.objects.get(user=user, tier=monthly_tier).status == 'active'


def test_unsubscribe_records_history(daily_tier, user):
    _apply_relation(_relation(), daily_tier, user)
    _apply_relation(_relation(update_type=2, transaction_id='TX-2'), daily_tier, user)

    assert SubscriptionHistory.objects.filter(user=user, action='cancelled').exists()


# --------------------------------------------------------------------------
# updateType 3
# --------------------------------------------------------------------------


def test_update_type_three_changes_nothing(daily_tier, user):
    """The guide defines 'Update' without saying what changes."""
    applied, description = _apply_relation(_relation(update_type=3), daily_tier, user)

    assert applied is False
    assert 'no subscription change' in description
    assert not SubscriptionPlan.objects.filter(user=user).exists()
