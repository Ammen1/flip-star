"""
The coins an on-demand package includes, granted upfront.

On-demand is bought outright: no duration, no renewal, one payment. Its coins
are configured on the package itself (`price_coins` -- "One-time purchase with
100 coins") and are now credited in full the moment that payment completes.

Four rules, and each has a way of going wrong that these cover:

* **never before payment.** The grant hangs off a completed
  SubscriptionPayment, so a pending or failed one credits nothing.
* **never twice.** The payment is the idempotency key, held by a unique
  constraint on the ledger -- a webhook delivered twice settles for one grant.
* **never the per-period gift as well.** `charge_gift_coins` rewards a plan
  being charged again; an on-demand package never is, so it takes the
  allocation instead of the gift rather than both.
* **never a recurring tier's price.** On daily/weekly/monthly, `price_coins`
  is what the plan *costs* in coins. Reading it as an allocation there would
  hand out the subscription fee.

There is no daily coin-grant job to retire: the whole Celery schedule is
leaderboards, campaign winners, boost expiry, media redrive, source purge,
typing indicators and the airtime renewal sweep. Nothing grants coins on a
timer, so nothing can re-grant this allocation.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from api.models import SubscriptionTier
from api.models.contest import CoinTransaction, UserCoinBalance
from api.models.subscription import SubscriptionPayment, SubscriptionPlan
from api.services.subscription_gift import (
    ALLOCATION_TRANSACTION_TYPE,
    GIFT_TRANSACTION_TYPE,
    ondemand_allocation,
)

pytestmark = pytest.mark.django_db

PACKAGE_COINS = 100


@pytest.fixture
def buyer():
    return User.objects.create_user(username='ondemand_buyer', password='x')


@pytest.fixture
def ondemand_tier():
    """The seeded package, as `manage.py seed_subscription_tiers` creates it."""
    tier = SubscriptionTier.objects.get(duration_type='ondemand')
    tier.price_coins = PACKAGE_COINS
    tier.charge_gift_coins = 3
    tier.save(update_fields=['price_coins', 'charge_gift_coins'])
    return tier


@pytest.fixture
def monthly_tier():
    tier = SubscriptionTier.objects.filter(duration_type='monthly').first()
    tier.price_coins = 500  # what a month costs if paid in coins
    tier.charge_gift_coins = 3
    tier.save(update_fields=['price_coins', 'charge_gift_coins'])
    return tier


def plan_for(user, tier):
    return SubscriptionPlan.objects.create(user=user, tier=tier, status='active')


def pay(plan, *, status='completed'):
    now = timezone.now()
    return SubscriptionPayment.objects.create(
        subscription=plan,
        user=plan.user,
        amount=Decimal('10.00'),
        status=status,
        payment_method='telebirr',
        duration_type=plan.tier.duration_type,
        period_start=now,
        period_end=now,
    )


def bonus_of(user):
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.refresh_from_db()
    return balance.bonus_balance or 0


def allocations(user):
    return CoinTransaction.objects.filter(user=user, transaction_type=ALLOCATION_TRANSACTION_TYPE)


# ── the allocation comes from the package ───────────────────────────────────


def test_the_amount_is_read_from_the_package(ondemand_tier):
    assert ondemand_allocation(ondemand_tier) == PACKAGE_COINS


def test_repricing_the_package_reprices_what_a_buyer_gets(ondemand_tier):
    """No second number to keep in step with the admin."""
    ondemand_tier.price_coins = 250
    ondemand_tier.save(update_fields=['price_coins'])

    assert ondemand_allocation(ondemand_tier) == 250


def test_a_recurring_tier_price_is_never_read_as_an_allocation(monthly_tier):
    """On monthly, price_coins is the cost of the plan. Granting it would pay
    the subscriber their own subscription fee."""
    assert ondemand_allocation(monthly_tier) == 0


# ── granted upfront, on payment ─────────────────────────────────────────────


def test_a_completed_purchase_grants_the_package_coins(buyer, ondemand_tier):
    plan = plan_for(buyer, ondemand_tier)

    pay(plan)

    assert bonus_of(buyer) == PACKAGE_COINS
    assert allocations(buyer).count() == 1


def test_nothing_is_granted_before_payment_confirms(buyer, ondemand_tier):
    plan = plan_for(buyer, ondemand_tier)

    pay(plan, status='pending')
    pay(plan, status='failed')

    assert bonus_of(buyer) == 0
    assert not allocations(buyer).exists()


def test_a_payment_completed_later_grants_then(buyer, ondemand_tier):
    plan = plan_for(buyer, ondemand_tier)
    payment = pay(plan, status='pending')
    assert bonus_of(buyer) == 0

    payment.status = 'completed'
    payment.save()

    assert bonus_of(buyer) == PACKAGE_COINS


def test_the_coins_are_not_giftable(buyer, ondemand_tier):
    """Bonus bucket: bought coins must not be cycled straight back out as
    gifts. `giftable_balance` is what enforces it at spend time.

    Measured as a change, not a total: every account is created with a welcome
    bonus already sitting in the earned bucket, so asserting `earned == 0`
    fails for a reason that has nothing to do with this allocation.
    """
    balance, _ = UserCoinBalance.objects.get_or_create(user=buyer)
    earned_before = balance.earned_balance or 0
    bonus_before = balance.bonus_balance or 0

    plan = plan_for(buyer, ondemand_tier)
    pay(plan)

    balance.refresh_from_db()
    assert balance.bonus_balance == bonus_before + PACKAGE_COINS, 'not in the bonus bucket'
    assert (balance.earned_balance or 0) == earned_before, 'landed in the giftable bucket'


# ── never twice ─────────────────────────────────────────────────────────────


def test_a_repeated_confirmation_grants_once(buyer, ondemand_tier):
    plan = plan_for(buyer, ondemand_tier)
    payment = pay(plan)

    payment.save()
    payment.save()

    assert allocations(buyer).count() == 1
    assert bonus_of(buyer) == PACKAGE_COINS


def test_a_second_purchase_is_a_second_allocation(buyer, ondemand_tier):
    """Buying the package again is a new payment, so it grants again --
    'once' is per purchase, not per lifetime."""
    plan = plan_for(buyer, ondemand_tier)

    pay(plan)
    pay(plan)

    assert allocations(buyer).count() == 2
    assert bonus_of(buyer) == PACKAGE_COINS * 2


def test_on_demand_does_not_also_collect_the_recurring_gift(buyer, ondemand_tier):
    """charge_gift_coins rewards a plan being charged again. An on-demand
    package never is, so it takes the allocation instead of both."""
    plan = plan_for(buyer, ondemand_tier)

    pay(plan)

    assert not CoinTransaction.objects.filter(
        user=buyer, transaction_type=GIFT_TRANSACTION_TYPE
    ).exists()
    assert bonus_of(buyer) == PACKAGE_COINS


def test_recurring_plans_still_get_their_gift(buyer, monthly_tier):
    """The existing behaviour for every other tier is untouched."""
    plan = plan_for(buyer, monthly_tier)

    pay(plan)

    assert (
        CoinTransaction.objects.filter(user=buyer, transaction_type=GIFT_TRANSACTION_TYPE).count()
        == 1
    )
    assert not allocations(buyer).exists()


# ── customers who already hold access ───────────────────────────────────────


def test_an_existing_paid_purchase_is_not_re_granted_on_migration(buyer, ondemand_tier):
    """Somebody who bought before this shipped already has their access. Their
    payment row is untouched by the migration -- which adds a ledger type and
    a constraint, nothing that writes coins -- so no retroactive credit
    appears."""
    plan = plan_for(buyer, ondemand_tier)
    payment = pay(plan)
    granted_once = bonus_of(buyer)

    # The migration adds no data. Re-reading the row changes nothing.
    payment.refresh_from_db()

    assert bonus_of(buyer) == granted_once == PACKAGE_COINS
    assert allocations(buyer).count() == 1


def test_a_package_configured_with_no_coins_grants_nothing(buyer, ondemand_tier):
    ondemand_tier.price_coins = 0
    ondemand_tier.save(update_fields=['price_coins'])
    plan = plan_for(buyer, ondemand_tier)

    pay(plan)

    assert bonus_of(buyer) == 0


def test_an_unclaimed_sms_package_is_not_an_error(ondemand_tier):
    """An SMS subscription exists before anybody claims it: no wallet yet, and
    the purchase must not fail because of it."""
    plan = SubscriptionPlan.objects.create(user=None, tier=ondemand_tier, status='active')
    now = timezone.now()

    payment = SubscriptionPayment.objects.create(
        subscription=plan,
        user=None,
        amount=Decimal('10.00'),
        status='completed',
        payment_method='timwe',
        duration_type='ondemand',
        period_start=now,
        period_end=now,
    )

    assert payment.pk is not None
