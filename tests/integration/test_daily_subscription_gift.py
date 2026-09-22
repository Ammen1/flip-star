"""
Gift coins arrive a day at a time, and add up to what the plan promised.

The product rule:

    daily    (1 day)    3                      -> 3
    weekly   (7 days)   4 4 4 4 3 3 3          -> 25
    monthly  (30 days)  4 every day            -> 120

The whole total used to land on the day of the charge, which left the rest of
the subscription with nothing in it. Two things must hold at once now, and a
test of either alone would miss what matters: **the daily amounts are right**,
and **they still sum to exactly the plan's total** -- a spread that quietly
loses the remainder short-changes every subscriber.

The days are counted from the period a **payment** covers, not from the plan.
A daily subscriber renews on the same plan row, so counting from the plan
would pay them once and never again however long they stayed -- the bug the
existing per-charge tests caught in the first version of this.

The property worth more than the arithmetic: a day pays **once**. The sweep
runs hourly, catches up days missed while the worker was down, and a webhook
can re-fire a charge at any time. None of that may pay twice.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from api.models.subscription import SubscriptionPayment, SubscriptionPlan, SubscriptionTier
from api.models.wallet import WalletConfig
from api.services.subscription_daily_gift import (
    coins_for_day,
    daily_schedule,
    day_index,
    grant_due,
    grant_for_day,
    schedule_for,
    sweep,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_welcome_bonus():
    """Every new account starts with a welcome bonus in the earned bucket,
    which would make these balance assertions meaningless."""
    config = WalletConfig.get_config()
    config.welcome_bonus = 0
    config.save()


@pytest.fixture
def subscriber():
    return User.objects.create_user(username='daily_gift_subscriber', password='x')


def tier(duration_type):
    return SubscriptionTier.objects.get(duration_type=duration_type)


def plan_for(user, duration_type, *, status='active'):
    return SubscriptionPlan.objects.create(
        user=user, tier=tier(duration_type), status=status, start_date=timezone.now()
    )


def period(plan, *, started_days_ago=0, status='completed'):
    """A payment covering one period of the plan.

    A ``completed`` one fires the post_save signal, which is how a real charge
    pays its first day -- so these are the real thing, not a stand-in. Tests
    that want to drive the days themselves use ``status='pending'``.
    """
    start = timezone.now() - timezone.timedelta(days=started_days_ago)
    days = plan.tier.duration_days or 1
    return SubscriptionPayment.objects.create(
        subscription=plan,
        user=plan.user,
        amount=Decimal('10.00'),
        status=status,
        payment_method='telebirr',
        duration_type=plan.tier.duration_type,
        period_start=start,
        period_end=start + timezone.timedelta(days=days),
    )


def earned(user):
    from api.models.contest import UserCoinBalance

    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.refresh_from_db()
    return balance.earned_balance or 0


def gifts(user):
    from api.models.contest import CoinTransaction

    return CoinTransaction.objects.filter(user=user, transaction_type='subscription_gift')


# ── the spread itself ────────────────────────────────────────────────────────


def test_the_shapes_the_product_asked_for():
    assert daily_schedule(3, 1) == [3]
    assert daily_schedule(25, 7) == [4, 4, 4, 4, 3, 3, 3]
    assert daily_schedule(120, 30) == [4] * 30


@pytest.mark.parametrize(
    ('duration_type', 'expected'),
    [('daily', [3]), ('weekly', [4, 4, 4, 4, 3, 3, 3]), ('monthly', [4] * 30)],
)
def test_each_plan_spreads_its_own_total(duration_type, expected):
    assert schedule_for(tier(duration_type)) == expected


@pytest.mark.parametrize(
    ('total', 'days'),
    [(25, 7), (120, 30), (3, 1), (1, 7), (100, 30), (7, 3), (0, 7), (13, 4)],
)
def test_the_days_always_add_up_to_the_total(total, days):
    """The property that matters more than any particular shape: a spread that
    rounds the remainder away short-changes every subscriber, quietly."""
    assert sum(daily_schedule(total, days)) == total


def test_the_extra_coins_land_on_the_earliest_days():
    """Front-loaded on purpose -- 4,4,4,4,3,3,3, not 3,3,3,3,3,3,7."""
    week = daily_schedule(25, 7)

    assert week == sorted(week, reverse=True)
    assert week[0] == 4


def test_a_total_smaller_than_the_period_still_pays_something():
    """1 coin over 7 days is one coin on day one, not nothing every day."""
    assert daily_schedule(1, 7) == [1, 0, 0, 0, 0, 0, 0]


def test_nothing_to_spread_pays_nothing():
    assert daily_schedule(0, 7) == []
    assert daily_schedule(25, 0) == []


@pytest.mark.parametrize(('day', 'expected'), [(1, 4), (4, 4), (5, 3), (7, 3), (8, 0), (0, 0)])
def test_what_a_given_day_of_a_week_pays(day, expected):
    assert coins_for_day(tier('weekly'), day) == expected


def test_on_demand_has_no_daily_spread():
    """Its coins are bought outright and granted at purchase instead."""
    assert schedule_for(tier('ondemand')) == []


# ── which day a period is on ─────────────────────────────────────────────────


def test_the_first_day_is_day_one(subscriber):
    charge = period(plan_for(subscriber, 'weekly'), status='pending')

    assert day_index(charge) == 1


def test_a_day_is_a_whole_day_from_when_the_period_started(subscriber):
    """Counted from period_start, so a subscription bought at 23:55 turns over
    at 23:55 the next night -- not five minutes later at midnight."""
    charge = period(plan_for(subscriber, 'weekly'), status='pending')
    start = charge.period_start

    assert day_index(charge, now=start + timezone.timedelta(hours=23, minutes=59)) == 1
    assert day_index(charge, now=start + timezone.timedelta(days=1)) == 2
    assert day_index(charge, now=start + timezone.timedelta(days=6)) == 7


# ── what a subscriber actually receives ──────────────────────────────────────


def test_a_weekly_subscriber_receives_the_week_a_day_at_a_time(subscriber):
    charge = period(plan_for(subscriber, 'weekly'), status='pending')

    running = 0
    for day, expected in enumerate([4, 4, 4, 4, 3, 3, 3], start=1):
        assert grant_for_day(charge, day) == expected, f'day {day}'
        running += expected
        assert earned(subscriber) == running

    assert earned(subscriber) == 25
    assert gifts(subscriber).count() == 7


def test_a_monthly_subscriber_receives_four_a_day_for_thirty_days(subscriber):
    charge = period(plan_for(subscriber, 'monthly'), status='pending')

    for day in range(1, 31):
        assert grant_for_day(charge, day) == 4

    assert earned(subscriber) == 120


def test_a_daily_subscriber_receives_three_on_their_one_day(subscriber):
    charge = period(plan_for(subscriber, 'daily'), status='pending')

    assert grant_for_day(charge, 1) == 3
    assert earned(subscriber) == 3


def test_a_day_beyond_the_period_pays_nothing(subscriber):
    charge = period(plan_for(subscriber, 'weekly'), status='pending')

    assert grant_for_day(charge, 8) == 0
    assert grant_for_day(charge, 99) == 0
    assert earned(subscriber) == 0


# ── one grant per day, whatever happens ──────────────────────────────────────


def test_the_same_day_is_never_paid_twice(subscriber):
    charge = period(plan_for(subscriber, 'weekly'), status='pending')

    assert grant_for_day(charge, 1) == 4
    assert grant_for_day(charge, 1) == 0
    assert grant_for_day(charge, 1) == 0

    assert earned(subscriber) == 4
    assert gifts(subscriber).count() == 1


def test_two_subscribers_on_the_same_day_are_both_paid(subscriber):
    """The key is per payment, so one subscriber's grant must not block
    everybody else's."""
    other = User.objects.create_user(username='another_subscriber', password='x')
    mine = period(plan_for(subscriber, 'weekly'), status='pending')
    theirs = period(plan_for(other, 'weekly'), status='pending')

    assert grant_for_day(mine, 1) == 4
    assert grant_for_day(theirs, 1) == 4


def test_a_renewal_pays_again(subscriber):
    """A renewal is a new payment covering new days, so it has new keys. This
    is what keeps a daily subscriber earning every day they keep paying."""
    plan = plan_for(subscriber, 'daily')

    period(plan)
    period(plan)
    period(plan)

    assert earned(subscriber) == 9, 'three charges, 3 coins each'
    assert gifts(subscriber).count() == 3


# ── the sweep ────────────────────────────────────────────────────────────────


def test_the_sweep_pays_what_is_due_today(subscriber):
    plan = plan_for(subscriber, 'weekly')
    charge = period(plan, status='pending')
    SubscriptionPayment.objects.filter(pk=charge.pk).update(status='completed')

    result = sweep()

    assert result['coins_granted'] == 4
    assert result['subscribers_paid'] == 1
    assert earned(subscriber) == 4


def test_running_the_sweep_again_pays_nothing_more(subscriber):
    """It runs hourly. Paying on each run would give a weekly subscriber 96
    coins on their first day instead of 4."""
    period(plan_for(subscriber, 'weekly'))

    second = sweep()

    assert second['coins_granted'] == 0
    assert earned(subscriber) == 4


def test_days_missed_while_nothing_was_running_are_caught_up(subscriber):
    """Vault sealed, the worker down, a deploy stuck: the days still happened
    and the subscriber still paid for them."""
    charge = period(plan_for(subscriber, 'weekly'), started_days_ago=3, status='pending')
    assert day_index(charge) == 4, 'started three days ago, so today is day four'
    SubscriptionPayment.objects.filter(pk=charge.pk).update(status='completed')
    charge.refresh_from_db()

    granted = grant_due(charge)

    assert granted == 16, 'days 1-4 at 4 each'
    assert gifts(subscriber).count() == 4


def test_catching_up_does_not_repay_a_day_that_landed(subscriber):
    charge = period(plan_for(subscriber, 'weekly'), started_days_ago=3, status='pending')
    SubscriptionPayment.objects.filter(pk=charge.pk).update(status='completed')
    charge.refresh_from_db()
    grant_for_day(charge, 2)

    granted = grant_due(charge)

    assert granted == 12, 'days 1, 3 and 4 -- not day 2 again'
    assert earned(subscriber) == 16, 'four days, paid once each'
    assert gifts(subscriber).count() == 4


def test_a_cancelled_subscriber_is_not_paid(subscriber):
    plan = plan_for(subscriber, 'weekly', status='cancelled')
    charge = period(plan, status='pending')
    SubscriptionPayment.objects.filter(pk=charge.pk).update(status='completed')

    sweep()

    assert earned(subscriber) == 0


def test_a_subscriber_in_grace_is_still_paid(subscriber):
    """Their renewal failed on balance; they have not cancelled, and the day
    they are owed was already paid for."""
    plan = plan_for(subscriber, 'weekly', status='grace_period')
    charge = period(plan, status='pending')
    SubscriptionPayment.objects.filter(pk=charge.pk).update(status='completed')

    sweep()

    assert earned(subscriber) == 4


def test_an_unpaid_charge_grants_nothing(subscriber):
    """A payment still pending is not a period anybody has paid for."""
    charge = period(plan_for(subscriber, 'weekly'), status='pending')

    assert grant_due(charge) == 0
    assert earned(subscriber) == 0


def test_on_demand_is_left_to_its_own_grant(subscriber):
    plan = plan_for(subscriber, 'ondemand')
    now = timezone.now()
    SubscriptionPayment.objects.create(
        subscription=plan,
        user=subscriber,
        amount=Decimal('10.00'),
        status='completed',
        payment_method='telebirr',
        duration_type='ondemand',
        period_start=now,
        period_end=now,
    )

    sweep()

    assert not gifts(subscriber).exists(), 'on-demand pays an allocation, not a daily gift'


# ── the charge itself ────────────────────────────────────────────────────────


def test_paying_for_a_week_gives_the_first_day_not_the_whole_week(subscriber):
    """The change, in one test: 4 coins on the day of the charge, not 25."""
    period(plan_for(subscriber, 'weekly'))

    assert earned(subscriber) == 4
    assert gifts(subscriber).count() == 1


def test_a_charge_saved_twice_still_pays_one_day(subscriber):
    """A webhook delivered twice re-saves the payment."""
    charge = period(plan_for(subscriber, 'weekly'))

    charge.save()
    charge.save()

    assert earned(subscriber) == 4


def test_the_week_completes_over_its_days(subscriber):
    """End to end: the charge pays day 1, the sweep pays the rest, and the
    subscriber ends the week with exactly what the plan promised."""
    charge = period(plan_for(subscriber, 'weekly'))
    start = charge.period_start

    for day in range(2, 8):
        sweep(now=start + timezone.timedelta(days=day - 1))

    assert earned(subscriber) == 25
    assert gifts(subscriber).count() == 7


def test_a_period_already_paid_in_full_the_old_way_is_not_paid_again(subscriber):
    """The transition: subscribers who received their whole 25 up front, under
    the rule this replaces, must not also receive it a day at a time."""
    from api.models.contest import UserCoinBalance

    charge = period(plan_for(subscriber, 'weekly'), status='pending')
    SubscriptionPayment.objects.filter(pk=charge.pk).update(status='completed')
    charge.refresh_from_db()
    balance, _ = UserCoinBalance.objects.get_or_create(user=subscriber)
    balance.add_earned(
        25,
        transaction_type='subscription_gift',
        payment_reference=str(charge.pk),
        description='paid the old way',
    )

    assert grant_due(charge) == 0
    assert earned(subscriber) == 25, 'still just the 25 they already had'
