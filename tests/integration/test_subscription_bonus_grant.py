"""
Granting the subscription bonus, and not granting it twice.

The tier says how many bonus coins it carries; activation credits them. The
interesting behaviour is the guard: activate() is reached from a first
purchase, a renewal, and a webhook the payment provider may deliver more than
once -- and a duplicate delivery must not pay a second time.

The coins land in the bonus bucket, which is what makes them unusable for
gifts. That restriction is covered in test_bonus_coins_not_giftable.py; here
the question is only whether they arrive, once, in the right place.
"""

import itertools

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from api.models.contest import UserCoinBalance
from api.models.subscription import SubscriptionPlan, SubscriptionTier

pytestmark = pytest.mark.django_db


@pytest.fixture
def subscriber():
    user = User.objects.create_user(username='subscriber', password='123456')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    # The welcome bonus from api/signals.py would otherwise muddy the figures.
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        earned_balance=0,
        bonus_balance=0,
        telebirr_purchased_balance=0,
        airtime_purchased_balance=0,
        purchased_balance=0,
        balance=0,
    )
    return user


#: name, slug and onevas_code are all unique, and migrations already seed the
#: real tiers -- so test tiers take a fresh suffix rather than colliding with
#: whatever the database was built with.
_tier_seq = itertools.count(1)


def make_tier(bonus_coins=0):
    n = next(_tier_seq)
    return SubscriptionTier.objects.create(
        name=f'TestTier{n}',
        slug=f'test-tier-{n}',
        duration_type='monthly',
        duration_days=30,
        price_etb=100,
        bonus_coins=bonus_coins,
        onevas_code=f'T{n}',
        spid='SP1',
        service_id='SV1',
    )


def bonus_of(user):
    return UserCoinBalance.objects.get(user=user).bonus_balance


# ---------------------------------------------------------------------------
# The grant
# ---------------------------------------------------------------------------


def test_activating_grants_the_tier_bonus(subscriber):
    plan = SubscriptionPlan.objects.create(user=subscriber, tier=make_tier(bonus_coins=500))

    plan.activate()

    assert bonus_of(subscriber) == 500


def test_the_coins_land_in_the_bonus_bucket_not_purchased(subscriber):
    """
    Where they land is the whole point.

    In `purchased` they would be giftable; in `bonus` they are not, and the
    gift endpoint refuses them.
    """
    plan = SubscriptionPlan.objects.create(user=subscriber, tier=make_tier(bonus_coins=500))

    plan.activate()

    balance = UserCoinBalance.objects.get(user=subscriber)
    assert balance.bonus_balance == 500
    assert balance.purchased_balance == 0
    assert balance.giftable_balance == 0
    assert balance.balance == 500


def test_a_tier_with_no_bonus_grants_nothing(subscriber):
    """
    The default. Every existing tier ships with bonus_coins=0, so this feature
    is inert until an admin configures a value -- no tier silently starts
    handing out coins on deploy.
    """
    plan = SubscriptionPlan.objects.create(user=subscriber, tier=make_tier(bonus_coins=0))

    plan.activate()

    assert bonus_of(subscriber) == 0


# ---------------------------------------------------------------------------
# Not twice
# ---------------------------------------------------------------------------


def test_activating_twice_in_one_period_grants_once(subscriber):
    """
    A retried webhook must not pay again.

    Payment providers redeliver; this repo has already been bitten by callbacks
    arriving more than once.
    """
    plan = SubscriptionPlan.objects.create(user=subscriber, tier=make_tier(bonus_coins=500))

    plan.activate()
    plan.activate()

    assert bonus_of(subscriber) == 500


def test_the_grant_is_stamped(subscriber):
    plan = SubscriptionPlan.objects.create(user=subscriber, tier=make_tier(bonus_coins=500))

    plan.activate()

    plan.refresh_from_db()
    assert plan.bonus_coins_granted_at is not None


def test_a_renewal_grants_the_next_period(subscriber):
    """
    A new period earns a new bonus.

    activate() moves start_date forward, and a stamp older than start_date is
    what marks the next grant due -- so the guard blocks repeats without
    blocking renewals.
    """
    plan = SubscriptionPlan.objects.create(user=subscriber, tier=make_tier(bonus_coins=500))
    plan.activate()
    assert bonus_of(subscriber) == 500

    # Stand in for the previous period having ended: the subscription lapsed,
    # and the bonus stamp was released for the next period.
    SubscriptionPlan.objects.filter(pk=plan.pk).update(
        status='expired', end_date=timezone.now() - timezone.timedelta(days=1)
    )
    plan.refresh_from_db()
    plan.clear_bonus_grant()

    plan.activate()

    assert bonus_of(subscriber) == 1000


def test_an_unclaimed_sms_subscription_grants_nothing(db):
    """
    SMS subscriptions exist before anyone claims them.

    There is no user, so there is no wallet to credit; this must not raise.
    """
    plan = SubscriptionPlan.objects.create(user=None, tier=make_tier(bonus_coins=500))

    plan.activate()

    plan.refresh_from_db()
    assert plan.bonus_coins_granted_at is None


# ---------------------------------------------------------------------------
# What the bonus can and cannot do, end to end
# ---------------------------------------------------------------------------


def test_granted_bonus_coins_cannot_fund_a_gift(subscriber):
    """The whole feature, in one line: granted, held, and refused for a gift."""
    plan = SubscriptionPlan.objects.create(user=subscriber, tier=make_tier(bonus_coins=500))
    plan.activate()

    balance = UserCoinBalance.objects.get(user=subscriber)
    with pytest.raises(ValueError, match='bonus coins cannot be used'):
        balance.spend_coins(50, 'gift_sent', restrict_earned=True)

    balance.refresh_from_db()
    assert balance.bonus_balance == 500


def test_granted_bonus_coins_can_fund_ordinary_actions(subscriber):
    """They are a real perk, just not a giftable one."""
    plan = SubscriptionPlan.objects.create(user=subscriber, tier=make_tier(bonus_coins=500))
    plan.activate()

    balance = UserCoinBalance.objects.get(user=subscriber)
    balance.spend_coins(120, 'boost')

    balance.refresh_from_db()
    assert balance.bonus_balance == 380
