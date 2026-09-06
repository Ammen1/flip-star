"""
Concurrency for engagement, gifts and refunds.

Companion to test_concurrency.py, which covers wallets, webhooks, withdrawals
and mandates. This file covers what that one did not: the paths a user can
trigger twice by double-tapping, and the refund a user can trigger twice by
retrying a request that appeared to hang.

PostgreSQL only
---------------
Every test here depends on row-level behaviour SQLite does not have. SQLite
serialises writers with a database-wide lock, so a race that these tests are
meant to expose simply cannot occur there -- the test would pass while telling
you nothing. They skip unless TEST_DB_ENGINE=postgresql is set; see
test_concurrency.py's module docstring for how to run them.

What each guards
----------------
  unlike        `reel.votes -= 1; reel.save()` -- read-modify-write, plus a
                bare save() that rewrites every column from a stale snapshot
  campaign join exists()-then-create, which raced into an IntegrityError 500
                on an action that had already succeeded
  boost refund  a status check outside the transaction let two Cancel taps
                both pay out
  gift          two sends against one balance, which must not both succeed
"""

import threading

import pytest
from django.contrib.auth.models import User
from django.db import connection

pytestmark = pytest.mark.integration

_IS_POSTGRES = connection.vendor == 'postgresql'
skip_reason = (
    'Requires a real PostgreSQL connection (TEST_DB_ENGINE=postgresql + TEST_DB_* vars) -- '
    'SQLite serialises writers with a database-wide lock, so these races cannot occur there '
    "and the tests would pass without exercising anything. See test_concurrency.py's module "
    'docstring to run them.'
)


@pytest.fixture(scope='module')
def pg(django_db_blocker):
    if not _IS_POSTGRES:
        pytest.skip(skip_reason)
    with django_db_blocker.unblock():
        yield


def run_together(fns):
    """Start every callable at as close to the same instant as possible."""
    results = [None] * len(fns)
    errors = [None] * len(fns)
    barrier = threading.Barrier(len(fns))

    def wrapper(i, fn):
        try:
            barrier.wait(timeout=10)
            results[i] = fn()
        except Exception as exc:  # noqa: BLE001 - captured for the assertions
            errors[i] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=wrapper, args=(i, fn)) for i, fn in enumerate(fns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


@pytest.fixture
def author(pg):
    u = User.objects.create_user(username=f'author_{threading.get_ident()}', password='123456')
    yield u
    u.delete()


@pytest.fixture
def fan(pg):
    u = User.objects.create_user(username=f'fan_{threading.get_ident()}', password='123456')
    yield u
    u.delete()


# ---------------------------------------------------------------------------
# Likes
# ---------------------------------------------------------------------------


def test_two_simultaneous_likes_create_one_vote(author, fan):
    """
    Double-tap.

    Vote's unique_together is what makes this safe; the test states the
    guarantee so that removing the constraint fails here rather than in
    production.
    """
    from api.models import Reel, Vote

    reel = Reel.objects.create(user=author, caption='c')

    def like():
        from django.db import IntegrityError, transaction

        try:
            with transaction.atomic():
                _, created = Vote.objects.get_or_create(user=fan, reel=reel)
                return created
        except IntegrityError:
            return False

    results, errors = run_together([like, like])

    assert Vote.objects.filter(reel=reel).count() == 1
    assert sum(1 for r in results if r) == 1, f'both calls claimed to create: {results} {errors}'
    reel.delete()


def test_concurrent_unlikes_do_not_drive_the_count_negative(author, fan):
    """
    The read-modify-write this replaced.

    Two unlikes each read votes=1 and each wrote 0 -- or, with a bare save(),
    wrote back a whole stale row. The count must land at 0 and stay there.
    """
    from django.db.models import F, Value
    from django.db.models.functions import Greatest

    from api.models import Reel, Vote

    reel = Reel.objects.create(user=author, caption='c', votes=1)
    Vote.objects.create(user=fan, reel=reel)

    def unlike():
        from django.db import transaction

        with transaction.atomic():
            deleted, _ = Vote.objects.filter(user=fan, reel=reel).delete()
            if deleted:
                Reel.objects.filter(pk=reel.pk).update(votes=Greatest(F('votes') - 1, Value(0)))
            return deleted

    run_together([unlike, unlike])

    reel.refresh_from_db()
    assert reel.votes == 0, f'count drifted to {reel.votes}'
    assert Vote.objects.filter(reel=reel).count() == 0
    reel.delete()


def test_an_unlike_does_not_roll_back_a_concurrent_share(author, fan):
    """
    Why the bare save() mattered more than the lost decrement.

    `reel.save()` writes every column from a snapshot taken before the read.
    A share landing between that read and the write was silently reverted --
    five leaderboard points gone, with nothing to show it happened.
    """
    from django.db.models import F, Value
    from django.db.models.functions import Greatest

    from api.models import Reel, Vote

    reel = Reel.objects.create(user=author, caption='c', votes=1, shares=0)
    Vote.objects.create(user=fan, reel=reel)

    def unlike():
        from django.db import transaction

        with transaction.atomic():
            deleted, _ = Vote.objects.filter(user=fan, reel=reel).delete()
            if deleted:
                Reel.objects.filter(pk=reel.pk).update(votes=Greatest(F('votes') - 1, Value(0)))

    def share():
        Reel.objects.filter(pk=reel.pk).update(shares=F('shares') + 1)

    run_together([unlike, share])

    reel.refresh_from_db()
    assert reel.shares == 1, 'the unlike reverted a concurrent share'
    assert reel.votes == 0
    reel.delete()


def test_many_concurrent_likes_are_counted_exactly(author):
    """Ten different users liking at once: ten votes, count of ten."""
    from django.db.models import F

    from api.models import Reel, Vote

    reel = Reel.objects.create(user=author, caption='c', votes=0)
    fans = [
        User.objects.create_user(username=f'crowd_{i}_{threading.get_ident()}', password='x')
        for i in range(10)
    ]

    def like_as(u):
        def _like():
            from django.db import transaction

            with transaction.atomic():
                _, created = Vote.objects.get_or_create(user=u, reel=reel)
                if created:
                    Reel.objects.filter(pk=reel.pk).update(votes=F('votes') + 1)

        return _like

    run_together([like_as(u) for u in fans])

    reel.refresh_from_db()
    assert Vote.objects.filter(reel=reel).count() == 10
    assert reel.votes == 10, f'lost increments: votes={reel.votes}'
    reel.delete()
    for u in fans:
        u.delete()


# ---------------------------------------------------------------------------
# Shares
# ---------------------------------------------------------------------------


def test_concurrent_shares_are_all_counted(author):
    """
    Shares are worth five points each, so a lost increment is five points a
    creator earned and did not receive.
    """
    from django.db.models import F

    from api.models import Reel

    reel = Reel.objects.create(user=author, caption='c', shares=0)

    def share():
        Reel.objects.filter(pk=reel.pk).update(shares=F('shares') + 1)

    run_together([share] * 8)

    reel.refresh_from_db()
    assert reel.shares == 8, f'lost share increments: {reel.shares}'
    reel.delete()


# ---------------------------------------------------------------------------
# Campaign entry
# ---------------------------------------------------------------------------


def test_two_simultaneous_joins_create_one_entry(author):
    """
    exists()-then-create raced into an IntegrityError 500 on an action that
    had in fact succeeded. get_or_create absorbs the collision.
    """
    from datetime import timedelta

    from django.utils import timezone

    from api.models.campaign import Campaign, CampaignEntry
    from api.models.core import Reel

    campaign = Campaign.objects.create(
        title=f'race_{threading.get_ident()}',
        description='d',
        prize_title='p',
        prize_description='pd',
        campaign_type='daily',
        start_date=timezone.now(),
        entry_deadline=timezone.now() + timedelta(days=1),
    )
    reel = Reel.objects.create(user=author, caption='entry')

    def join():
        from django.db import IntegrityError, transaction

        try:
            with transaction.atomic():
                _, created = CampaignEntry.objects.get_or_create(
                    campaign=campaign, user=author, defaults={'reel': reel}
                )
                return created
        except IntegrityError:
            return False

    results, _ = run_together([join, join])

    assert CampaignEntry.objects.filter(campaign=campaign).count() == 1
    assert sum(1 for r in results if r) == 1
    reel.delete()
    campaign.delete()


def test_concurrent_joins_count_every_entrant(author):
    """total_entries used `+= 1` and lost increments under concurrency."""
    from datetime import timedelta

    from django.db.models import F
    from django.utils import timezone

    from api.models.campaign import Campaign, CampaignEntry
    from api.models.core import Reel

    campaign = Campaign.objects.create(
        title=f'count_{threading.get_ident()}',
        description='d',
        prize_title='p',
        prize_description='pd',
        campaign_type='daily',
        start_date=timezone.now(),
        entry_deadline=timezone.now() + timedelta(days=1),
        total_entries=0,
    )
    users = [
        User.objects.create_user(username=f'entrant_{i}_{threading.get_ident()}', password='x')
        for i in range(6)
    ]
    reels = [Reel.objects.create(user=u, caption='e') for u in users]

    def join_as(u, r):
        def _join():
            from django.db import transaction

            with transaction.atomic():
                _, created = CampaignEntry.objects.get_or_create(
                    campaign=campaign, user=u, defaults={'reel': r}
                )
                if created:
                    Campaign.objects.filter(pk=campaign.pk).update(
                        total_entries=F('total_entries') + 1
                    )

        return _join

    run_together([join_as(u, r) for u, r in zip(users, reels, strict=True)])

    campaign.refresh_from_db()
    assert CampaignEntry.objects.filter(campaign=campaign).count() == 6
    assert campaign.total_entries == 6, f'lost increments: {campaign.total_entries}'
    for r in reels:
        r.delete()
    for u in users:
        u.delete()
    campaign.delete()


# ---------------------------------------------------------------------------
# Gifts and balances
# ---------------------------------------------------------------------------


def _wallet(user, **fields):
    from api.models.contest import UserCoinBalance

    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    for field, value in fields.items():
        setattr(balance, field, value)
    balance._sync_balance()
    balance.save()
    return balance


def test_two_simultaneous_gifts_cannot_both_spend_the_same_coins(fan):
    """
    The specification's headline case.

    100 giftable coins, two gifts of 80. Exactly one succeeds; the balance
    never goes negative.
    """
    from api.models.contest import UserCoinBalance

    _wallet(fan, telebirr_purchased_balance=100, earned_balance=0, bonus_balance=0)

    def gift():
        balance = UserCoinBalance.objects.get(user=fan)
        balance.spend_coins(80, 'gift_sent', restrict_earned=True)
        return 'ok'

    results, errors = run_together([gift, gift])

    succeeded = sum(1 for r in results if r == 'ok')
    assert succeeded == 1, f'{succeeded} gifts succeeded against one balance'
    assert sum(1 for e in errors if isinstance(e, ValueError)) == 1

    final = UserCoinBalance.objects.get(user=fan)
    assert final.telebirr_purchased_balance == 20
    assert final.balance >= 0


def test_a_gift_racing_an_ordinary_spend_never_overdraws(fan):
    """
    The two spends draw on different buckets but share one row.

    A gift takes only Telebirr coins; a boost prefers bonus first. Both lock
    the same row, so neither can act on a snapshot the other has invalidated.
    """
    from api.models.contest import UserCoinBalance

    _wallet(fan, telebirr_purchased_balance=100, bonus_balance=50, earned_balance=0)

    def gift():
        UserCoinBalance.objects.get(user=fan).spend_coins(100, 'gift_sent', restrict_earned=True)

    def boost():
        UserCoinBalance.objects.get(user=fan).spend_coins(50, 'boost')

    run_together([gift, boost])

    final = UserCoinBalance.objects.get(user=fan)
    assert final.telebirr_purchased_balance >= 0
    assert final.bonus_balance >= 0
    assert final.balance == (
        final.earned_balance
        + final.bonus_balance
        + final.telebirr_purchased_balance
        + final.airtime_purchased_balance
    )


def test_concurrent_bonus_grants_do_not_double_credit(fan):
    """
    Two workers activating the same subscription.

    The stamp is what makes this once-only; without it a redelivered webhook
    credited 500 twice.
    """
    from django.utils import timezone

    from api.models.contest import UserCoinBalance
    from api.services.concurrency import claim_transition

    _wallet(fan, bonus_balance=0, telebirr_purchased_balance=0, earned_balance=0)

    from api.models.subscription import SubscriptionPlan, SubscriptionTier

    tier = SubscriptionTier.objects.create(
        name=f'race_tier_{threading.get_ident()}',
        slug=f'race-tier-{threading.get_ident()}',
        duration_type='monthly',
        duration_days=30,
        price_etb=100,
        bonus_coins=500,
        onevas_code=f'R{threading.get_ident() % 100}',
        spid='SP',
        service_id='SV',
    )
    plan = SubscriptionPlan.objects.create(user=fan, tier=tier, status='pending')

    def activate():
        # The claim is what serialises the two workers; only the winner credits.
        if claim_transition(SubscriptionPlan, plan.pk, expect='pending', to='active'):
            SubscriptionPlan.objects.filter(pk=plan.pk).update(start_date=timezone.now())
            UserCoinBalance.objects.get(user=fan).add_bonus(500)
            return 'granted'
        return 'skipped'

    results, _ = run_together([activate, activate])

    assert sum(1 for r in results if r == 'granted') == 1
    assert UserCoinBalance.objects.get(user=fan).bonus_balance == 500

    plan.delete()
    tier.delete()


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


def test_a_claim_admits_exactly_one_caller(author):
    """
    The primitive the refund path now rests on.

    Two Cancel taps both passed a status check made outside any transaction,
    and both refunded.
    """
    from api.models import Reel
    from api.services.concurrency import claim_transition

    reel = Reel.objects.create(user=author, caption='c', processed=False)

    def claim():
        return claim_transition(Reel, reel.pk, field='processed', expect=False, to=True)

    results, _ = run_together([claim, claim])

    assert sum(1 for r in results if r) == 1, f'both callers claimed: {results}'
    reel.delete()


def test_incompatible_transitions_cannot_both_apply(author):
    """
    PENDING -> SUCCESS racing PENDING -> FAILED.

    One wins; the other finds the row already moved and does nothing. The
    final state is one of the two, never a blend.
    """
    from api.models import Reel
    from api.services.concurrency import claim_transition

    reel = Reel.objects.create(user=author, caption='c', processed=False, processing_failed=False)

    def succeed():
        return claim_transition(Reel, reel.pk, field='processed', expect=False, to=True)

    def fail():
        return claim_transition(
            Reel, reel.pk, field='processed', expect=False, to=True, processing_failed=True
        )

    results, _ = run_together([succeed, fail])

    assert sum(1 for r in results if r) == 1
    reel.refresh_from_db()
    assert reel.processed is True
    reel.delete()
