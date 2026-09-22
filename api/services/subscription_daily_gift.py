"""
Gift coins paid out a day at a time, instead of all at once.

What changed and why: a subscriber used to receive their plan's whole gift the
moment a charge completed -- 25 coins on day one of a weekly plan, 120 on day
one of a monthly one. Paid that way the reward has nothing to do with the days
that follow, and somebody who takes the coins on day one has no reason to come
back on day two. Spreading it gives every day of the subscription something in
it, for the same money.

The amounts are the plan's own total, spread across the days it lasts:

    daily    (1 day)    3                      -> 3
    weekly   (7 days)   4 4 4 4 3 3 3          -> 25
    monthly  (30 days)  4 every day            -> 120

Those are not three hardcoded lists. Each is ``total // days`` per day with the
remainder handed out one coin at a time from day one, which is what makes
weekly 4,4,4,4,3,3,3 rather than 3,3,3,3,3,3,7. Change a plan's total in the
admin and the spread follows; nothing here needs editing, and there is no
second copy of the numbers to drift.

Front-loaded deliberately: the extra coins land on the days a new subscriber is
deciding whether the plan was worth it, and the arithmetic stays exact -- the
parts always sum to the total, so nobody is short-changed by rounding.

Anchored on the **payment**, not the plan. A daily subscriber renews on the
same plan row -- ``start_date`` never moves -- so counting days from the plan
would pay them on day one and never again, however long they stayed. Every
charge writes its own period (``period_start`` / ``period_end``), which is
exactly "the days this subscriber has paid for", so that is what the days
are counted from and what a renewal resets.

**One grant per day, ever.** The idempotency key is the payment and the day,
held by the same unique constraint on the coin ledger that the per-charge gift
used (``one_subscription_gift_per_payment`` covers
``transaction_type='subscription_gift'`` + ``payment_reference``). A task that
runs twice, two workers racing, or a retry after a crash all end with one row,
because the second insert is refused by the database rather than by a check in
Python.

On-demand is not part of this. Its coins are bought outright and granted once
at purchase (``subscription_gift.grant_ondemand_allocation``).
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: The ledger type these grants are written under -- the same one the
#: per-charge gift used, so a subscriber's gift history stays in one place.
GIFT_TRANSACTION_TYPE = 'subscription_gift'

#: Plans whose coins come from a package rather than from the days they last.
ONDEMAND = 'ondemand'

#: What a plan lasts when the tier does not say. Mirrors the seeded tiers, so
#: a tier missing duration_days still pays the right shape rather than nothing.
FALLBACK_DAYS = {'daily': 1, 'weekly': 7, 'monthly': 30}


def plan_days(tier) -> int:
    """How many days one period of this plan covers."""
    if tier is None or getattr(tier, 'duration_type', None) == ONDEMAND:
        return 0
    days = getattr(tier, 'duration_days', None)
    if days is None:
        days = FALLBACK_DAYS.get(getattr(tier, 'duration_type', ''), 0)
    return max(0, int(days or 0))


def plan_total(tier) -> int:
    """The gift coins one period of this plan is worth in total."""
    if tier is None:
        return 0
    return max(0, int(getattr(tier, 'charge_gift_coins', 0) or 0))


def daily_schedule(total: int, days: int) -> list[int]:
    """`total` coins split across `days`, remainder on the earliest days.

        >>> daily_schedule(25, 7)
        [4, 4, 4, 4, 3, 3, 3]
        >>> daily_schedule(120, 30)[:3]
        [4, 4, 4]
        >>> daily_schedule(3, 1)
        [3]

    The parts always sum to `total`: the remainder is distributed rather than
    rounded away, so the subscriber receives exactly what the plan promises.
    """
    if total <= 0 or days <= 0:
        return []
    base, extra = divmod(total, days)
    return [base + 1 if day < extra else base for day in range(days)]


def schedule_for(tier) -> list[int]:
    """The per-day amounts for this plan."""
    return daily_schedule(plan_total(tier), plan_days(tier))


def coins_for_day(tier, day: int) -> int:
    """What day `day` of this plan pays. Day 1 is the first day.

    A day outside the plan's length pays nothing -- that is the ordinary way a
    period ends, not an error.
    """
    if day < 1:
        return 0
    schedule = schedule_for(tier)
    return schedule[day - 1] if day <= len(schedule) else 0


def tier_of(payment):
    """The plan's tier, which says what a period is worth and how long it runs."""
    plan = getattr(payment, 'subscription', None)
    return getattr(plan, 'tier', None)


def day_index(payment, now=None) -> int:
    """Which day of its period a payment is on. Day 1 is the first day.

    Counted from ``period_start`` in whole days, so a subscription bought at
    23:55 moves to day 2 at 23:55 the next night rather than five minutes
    later at midnight.
    """
    start = getattr(payment, 'period_start', None)
    if start is None:
        return 0
    now = now or timezone.now()
    elapsed = now - start
    if elapsed.total_seconds() < 0:
        return 0
    return elapsed.days + 1


def reference_for(payment, day: int) -> str:
    """The idempotency key: this payment, this day. One grant, whatever happens."""
    return f'sub-gift:{payment.pk}:day:{day}'


def already_granted(payment, day: int) -> bool:
    """Has this day already paid out? Read-only; the constraint decides."""
    from api.models.contest import CoinTransaction

    return CoinTransaction.objects.filter(
        transaction_type=GIFT_TRANSACTION_TYPE, payment_reference=reference_for(payment, day)
    ).exists()


def paid_in_full_by_the_old_rule(payment) -> bool:
    """Did this period already pay its whole total, the way it used to?

    Before the spread, a charge granted the entire period on day one, keyed on
    the payment's own id. Those subscribers have had their 25 or 120 coins;
    paying them again a day at a time would pay twice for the same week. This
    matters only while periods bought under the old rule are still running.
    """
    from api.models.contest import CoinTransaction

    return CoinTransaction.objects.filter(
        transaction_type=GIFT_TRANSACTION_TYPE, payment_reference=str(payment.pk)
    ).exists()


def grant_for_day(payment, day: int) -> int:
    """Give a subscriber the coins for one day they paid for. Returns how many.

    Returns 0 -- without raising -- when there is nothing to give: the day is
    outside the period, the subscription has no user yet (an SMS subscription
    exists before anybody claims it), or the day has already been paid. None
    of those are errors.
    """
    tier = tier_of(payment)
    coins = coins_for_day(tier, day)
    if not coins:
        return 0

    plan = getattr(payment, 'subscription', None)
    user_id = getattr(payment, 'user_id', None) or getattr(plan, 'user_id', None)
    if not user_id:
        return 0

    from api.models.contest import UserCoinBalance

    try:
        with transaction.atomic():
            balance, _ = UserCoinBalance.objects.get_or_create(user_id=user_id)
            balance.add_earned(
                coins,
                transaction_type=GIFT_TRANSACTION_TYPE,
                payment_reference=reference_for(payment, day),
                description=f'{tier.name} subscription gift (day {day})',
            )
    except IntegrityError:
        # The unique constraint refused a second grant for this day. That is
        # the guard doing its job, not a failure.
        logger.info(
            'SUBSCRIPTION_DAILY_GIFT_ALREADY_GRANTED',
            extra={'payment_id': str(payment.pk), 'day': day, 'user_id': user_id},
        )
        return 0

    logger.info(
        'SUBSCRIPTION_DAILY_GIFT_GRANTED',
        extra={'payment_id': str(payment.pk), 'day': day, 'user_id': user_id, 'coins': coins},
    )
    return coins


#: Statuses that still earn. `grace_period` is a subscriber whose renewal
#: failed on balance and who keeps read-only access for 24 hours -- they have
#: not cancelled, and the day they are owed was already paid for.
EARNING_STATUSES = ('active', 'grace_period')


def grant_due(payment, now=None) -> int:
    """Pay whatever this period owes today. Returns the coins granted.

    Also catches up: if the sweep did not run yesterday -- the worker was down,
    Vault was sealed, the cluster was mid-deploy -- the missed days are paid
    now rather than lost. Every day is keyed separately, so catching up cannot
    double-pay a day that did land.
    """
    if getattr(payment, 'status', None) != 'completed':
        return 0

    plan = getattr(payment, 'subscription', None)
    if plan is not None and getattr(plan, 'status', None) not in EARNING_STATUSES:
        return 0

    if paid_in_full_by_the_old_rule(payment):
        return 0

    today = day_index(payment, now=now)
    if today < 1:
        return 0

    granted = 0
    for day in range(1, min(today, len(schedule_for(tier_of(payment)))) + 1):
        granted += grant_for_day(payment, day)
    return granted


def sweep(now=None) -> dict:
    """Pay every subscriber for the day of the period they are in.

    Runs from the daily beat task. Iterates rather than doing it in one query
    because each grant is its own transaction: one subscriber's failure must
    not stop the rest being paid.
    """
    from api.models.subscription import SubscriptionPayment

    moment = now or timezone.now()
    payments = (
        SubscriptionPayment.objects.filter(
            status='completed',
            period_start__lte=moment,
            period_end__gte=moment,
            subscription__status__in=EARNING_STATUSES,
        )
        .exclude(subscription__tier__isnull=True)
        .exclude(subscription__tier__duration_type=ONDEMAND)
        .select_related('subscription', 'subscription__tier')
    )

    paid = coins = 0
    for payment in payments.iterator():
        try:
            granted = grant_due(payment, now=now)
        except Exception:
            logger.exception('SUBSCRIPTION_DAILY_GIFT_SWEEP_FAILED payment=%s', payment.pk)
            continue
        if granted:
            paid += 1
            coins += granted

    logger.info('SUBSCRIPTION_DAILY_GIFT_SWEEP subscribers=%s coins=%s', paid, coins)
    return {'subscribers_paid': paid, 'coins_granted': coins}
