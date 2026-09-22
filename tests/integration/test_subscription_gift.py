"""
The gift coins a subscriber earns by paying.

The reward used to be for logging in: open the app, claim 3 coins, keep a
streak alive. It now follows the money -- one gift each time a subscription
charge completes, so a daily plan is gifted daily and a monthly plan monthly.

The two things worth pinning are that every charge pays once, and that no
charge pays twice. The second matters more: a Telebirr webhook is delivered
more than once, the renewal sweep retries, and two workers can settle the
same payment at the same moment. The guard is a unique constraint on the coin
ledger rather than a check in Python, so these drive real saves and let the
database answer.
"""

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from api.models import SubscriptionTier
from api.models.contest import CoinTransaction, UserCoinBalance
from api.models.subscription import SubscriptionPayment, SubscriptionPlan
from api.services.subscription_gift import GIFT_TRANSACTION_TYPE, grant_for_payment

pytestmark = pytest.mark.django_db

GIFT = 3


@pytest.fixture
def subscriber():
    return User.objects.create_user(username='gift_subscriber', password='x')


@pytest.fixture
def tier():
    """The seeded daily tier, gifting what the login bonus used to pay."""
    row = SubscriptionTier.objects.filter(duration_type='daily').first()
    row.charge_gift_coins = GIFT
    row.save(update_fields=['charge_gift_coins'])
    return row


@pytest.fixture
def plan(subscriber, tier):
    return SubscriptionPlan.objects.create(user=subscriber, tier=tier, status='active')


def coins_of(user):
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.refresh_from_db()
    return balance.earned_balance or 0


def gifts_for(user):
    return CoinTransaction.objects.filter(user=user, transaction_type=GIFT_TRANSACTION_TYPE)


def charge(plan, *, status='completed'):
    """A charge, as every payment path records one."""
    now = timezone.now()
    return SubscriptionPayment.objects.create(
        subscription=plan,
        user=plan.user,
        amount=3,
        status=status,
        payment_method='timwe',
        duration_type=plan.tier.duration_type,
        period_start=now,
        period_end=now + timezone.timedelta(days=1),
    )


def test_a_completed_charge_gifts_coins(plan, subscriber):
    before = coins_of(subscriber)

    charge(plan)

    assert coins_of(subscriber) == before + GIFT


def test_the_gift_arrives_without_anybody_claiming_it(plan, subscriber):
    """The point of the change: no endpoint to call, no streak to keep."""
    charge(plan)

    assert gifts_for(subscriber).count() == 1


def test_every_charge_is_gifted_not_just_the_first(plan, subscriber):
    """A daily subscriber is charged daily, so they are gifted daily. The
    older tier bonus paid once per plan and never again -- this does not."""
    before = coins_of(subscriber)

    charge(plan)
    charge(plan)
    charge(plan)

    assert gifts_for(subscriber).count() == 3
    assert coins_of(subscriber) == before + 3 * GIFT


def test_the_same_charge_cannot_pay_twice(plan, subscriber):
    """A webhook delivered twice, or a retried task, re-saves the payment."""
    payment = charge(plan)
    before = coins_of(subscriber)

    payment.save()
    payment.save()
    grant_for_payment(payment)

    assert gifts_for(subscriber).count() == 1
    assert coins_of(subscriber) == before, 'a repeat delivery paid again'


def test_a_charge_that_did_not_complete_gifts_nothing(plan, subscriber):
    before = coins_of(subscriber)

    charge(plan, status='pending')
    charge(plan, status='failed')

    assert coins_of(subscriber) == before
    assert not gifts_for(subscriber).exists()


def test_a_payment_completed_later_is_gifted_then(plan, subscriber):
    """Some paths write the row pending and complete it afterwards."""
    payment = charge(plan, status='pending')
    assert not gifts_for(subscriber).exists()

    payment.status = 'completed'
    payment.save()

    assert gifts_for(subscriber).count() == 1


def test_a_tier_that_gifts_nothing_pays_nothing(plan, subscriber, tier):
    tier.charge_gift_coins = 0
    tier.save(update_fields=['charge_gift_coins'])
    before = coins_of(subscriber)

    charge(plan)

    assert coins_of(subscriber) == before


def test_the_coins_are_spendable_like_the_login_bonus_was(plan, subscriber):
    """Granted as earned, not bonus. The tier's `bonus_coins` land in a bucket
    that cannot be spent on gifts; this reward could be, and still can.

    Measured as a change rather than a total: every account starts with a
    welcome bonus already sitting in the earned bucket, so the first version
    of this test asserted `earned_balance >= GIFT` and passed even with the
    gift switched off entirely.
    """
    balance = UserCoinBalance.objects.get(user=subscriber)
    earned_before = balance.earned_balance or 0
    bonus_before = balance.bonus_balance or 0

    charge(plan)

    balance.refresh_from_db()
    assert balance.earned_balance == earned_before + GIFT, 'not in the spendable bucket'
    assert (balance.bonus_balance or 0) == bonus_before, 'landed in the non-giftable bucket'


def test_a_subscription_with_no_user_yet_is_not_an_error(tier):
    """An SMS subscription exists before anybody claims it: no wallet to
    credit, and that must not break the charge that just succeeded."""
    plan = SubscriptionPlan.objects.create(user=None, tier=tier, status='active')

    payment = charge(plan)

    assert payment.pk is not None
    assert grant_for_payment(payment) == 0


def test_the_gift_is_traceable_to_the_charge_that_paid_for_it(plan, subscriber):
    """The reference now carries the day as well as the charge, because a
    period pays a day at a time (api/services/subscription_daily_gift.py). A
    daily plan is one day long, so its charge still produces exactly one row."""
    payment = charge(plan)

    gift = gifts_for(subscriber).get()
    assert str(payment.pk) in gift.payment_reference
    assert gift.payment_reference.endswith(':day:1')
    assert gift.coins == GIFT
