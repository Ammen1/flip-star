"""The per-charge gift coins each recurring plan pays.

A subscriber earns gift coins ("bones") every time a payment on their plan
completes -- the first subscription and each renewal charge alike. The amount
lives on the tier (`SubscriptionTier.charge_gift_coins`) and is paid out by
the post_save signal on SubscriptionPayment (api/services/subscription_gift.py).

The daily plan already rewarded every charge this way (3, what the login bonus
used to pay). Migration 0127 gives weekly 25 and monthly 120 per charge (0135 later
corrects weekly to 23, the 4/4/3/3/3/3/3 the plan promises) and
zeros on-demand, whose package pays its coins outright instead (`test_ondemand_allocation`). These tests pin the shipped amounts and the
charging-side payout so the numbers cannot drift.

The payout itself is now spread across the days of the period rather than
paid in one lump on the day of the charge -- see
tests/integration/test_daily_subscription_gift.py. What these still pin is
the per-plan **total**, which is what the days add up to.
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


@pytest.mark.parametrize(
    'slug,expected',
    [
        ('daily', 3),
        ('weekly', 23),
        ('monthly', 120),
        ('ondemand', 0),
    ],
)
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


@pytest.mark.parametrize('slug,first_day,total', [('weekly', 4, 23), ('monthly', 4, 120)])
def test_each_charge_starts_paying_its_plan_gift(subscriber, slug, first_day, total):
    """A completed payment pays the period's **first day**, not the whole
    period. The rest arrive daily (api/services/subscription_daily_gift.py,
    tests/integration/test_daily_subscription_gift.py); the plan's total is
    still what the days add up to."""
    from api.services.subscription_daily_gift import schedule_for

    tier = SubscriptionTier.objects.get(duration_type=slug)
    plan = SubscriptionPlan.objects.create(user=subscriber, tier=tier, status='active')

    pay(plan)
    assert gift_balance(subscriber) == first_day
    assert gifts(subscriber).count() == 1

    # A renewal is a new payment covering new days, so it pays its day one too.
    pay(plan)
    assert gift_balance(subscriber) == first_day * 2
    assert gifts(subscriber).count() == 2

    assert sum(schedule_for(tier)) == total, 'the period is still worth its total'


@pytest.mark.parametrize('slug', ['weekly', 'monthly'])
def test_an_unconfirmed_charge_grants_nothing(subscriber, slug):
    plan = SubscriptionPlan.objects.create(
        user=subscriber, tier=SubscriptionTier.objects.get(duration_type=slug), status='active'
    )

    pay(plan, status='pending')
    pay(plan, status='failed')

    assert gift_balance(subscriber) == 0
    assert not gifts(subscriber).exists()


# ── the reported case: every plan still paying 3 ────────────────────────────


def _migration_0128():
    import importlib

    return importlib.import_module('api.migrations.0128_charge_gift_amounts_by_plan_type')


@pytest.fixture
def renamed_tiers_all_paying_three():
    """The database the report came from: tiers whose slugs are not the seed
    ones, every one still at the 3 coins 0123 gave all of them. 0127 looked
    for slug='weekly' / 'monthly', matched nothing and changed nothing."""
    slugs = {
        'daily': 'daily-premium-plan',
        'weekly': 'weekly-premium-plan',
        'monthly': 'monthly-premium-plan',
    }
    for duration_type, slug in slugs.items():
        SubscriptionTier.objects.filter(duration_type=duration_type).update(
            slug=slug, charge_gift_coins=3
        )


def test_tiers_with_other_slugs_get_their_plan_amounts(renamed_tiers_all_paying_three):
    """0128's own output, which is what this test is about.

    Weekly is 25 here and not the shipped 23: this drives 0128 in isolation to
    prove it finds tiers by duration_type rather than by slug. Migration 0135
    corrects weekly afterwards, and the shipped figure is asserted by
    test_the_per_charge_gift_amounts above.
    """
    from django.apps import apps

    _migration_0128().set_gifts(apps, None)

    for duration_type, expected in (('daily', 3), ('weekly', 25), ('monthly', 120)):
        tier = SubscriptionTier.objects.get(duration_type=duration_type)
        assert tier.charge_gift_coins == expected, f'{tier.slug} pays {tier.charge_gift_coins}'


def test_a_weekly_subscriber_is_then_paid_from_25_not_3(renamed_tiers_all_paying_three, subscriber):
    """End to end on the renamed tiers: the week is worth more than 3, and its
    first day pays 4 -- where before migration 0128 the whole week was 3.

    Drives 0128 alone, so the total here is its 25 rather than the shipped 23
    that 0135 settles on. The shape assertion is what this is really about.
    """
    from django.apps import apps

    from api.services.subscription_daily_gift import schedule_for

    _migration_0128().set_gifts(apps, None)
    tier = SubscriptionTier.objects.get(duration_type='weekly')
    plan = SubscriptionPlan.objects.create(user=subscriber, tier=tier, status='active')

    pay(plan)

    assert schedule_for(tier) == [4, 4, 4, 4, 3, 3, 3]
    assert gift_balance(subscriber) == 4, 'day one'


def test_an_amount_set_in_the_admin_is_left_alone():
    """Only tiers still at the seeded 3 are changed; a deliberate choice stays."""
    from django.apps import apps

    SubscriptionTier.objects.filter(duration_type='weekly').update(charge_gift_coins=40)

    _migration_0128().set_gifts(apps, None)

    assert SubscriptionTier.objects.get(duration_type='weekly').charge_gift_coins == 40
