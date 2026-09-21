"""The per-charge gift coins each recurring plan pays.

A subscriber earns gift coins ("bones") every time a payment on their plan
completes -- the first subscription and each renewal charge alike. The amount
lives on the tier (`SubscriptionTier.charge_gift_coins`) and is paid out by
the post_save signal on SubscriptionPayment (api/services/subscription_gift.py).

The daily plan already rewarded every charge this way (3, what the login bonus
used to pay). Migration 0127 gives weekly 25 and monthly 120 per charge and
zeros on-demand, whose package pays its coins outright instead (`test_ondemand_allocation`). These tests pin the shipped amounts and the
charging-side payout so the numbers cannot drift.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from api.models.subscription import SubscriptionPayment, SubscriptionPlan, SubscriptionTier
from api.models.wallet import WalletConfig
from api.services.subscription_gift import GIFT_TRANSACTION_TYPE, gift_coins_for

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def disable_welcome_bonus():
    """Keep earned_balance assertions clean: every account is created with a
    welcome bonus already sitting in the earned bucket."""
    config = WalletConfig.get_config()
    config.welcome_bonus = 0
    config.save()


@pytest.mark.parametrize('slug,expected', [
    ('daily', 3),
    ('weekly', 25),
    ('monthly', 120),
    ('ondemand', 0),
])
def test_the_per_charge_gift_amounts(slug, expected):
    tier = SubscriptionTier.objects.get(duration_type=slug)
    assert gift_coins_for(tier) == expected


@pytest.fixture
def subscriber():
    return User.objects.create_user(username='bones_subscriber', password='x')


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


def gift_balance(user):
    from api.models.contest import UserCoinBalance

    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.refresh_from_db()
    return balance.earned_balance or 0


def gifts(user):
    from api.models.contest import CoinTransaction

    return CoinTransaction.objects.filter(user=user, transaction_type=GIFT_TRANSACTION_TYPE)


@pytest.mark.parametrize('slug,amount', [('weekly', 25), ('monthly', 120)])
def test_each_charge_pays_its_plan_gift(subscriber, slug, amount):
    """A completed payment on the seeded tier pays the plan's gift out -- on
    first subscription and again on each renewal charge."""
    plan = SubscriptionPlan.objects.create(
        user=subscriber, tier=SubscriptionTier.objects.get(duration_type=slug), status='active'
    )

    pay(plan)
    assert gift_balance(subscriber) == amount
    assert gifts(subscriber).count() == 1

    # a renewal is a new completed payment, so it pays out again
    pay(plan)
    assert gift_balance(subscriber) == amount * 2
    assert gifts(subscriber).count() == 2


@pytest.mark.parametrize('slug', ['weekly', 'monthly'])
def test_an_unconfirmed_charge_grants_nothing(subscriber, slug):
    plan = SubscriptionPlan.objects.create(
        user=subscriber, tier=SubscriptionTier.objects.get(duration_type=slug), status='active'
    )

    pay(plan, status='pending')
    pay(plan, status='failed')

    assert gift_balance(subscriber) == 0
    assert not gifts(subscriber).exists()
