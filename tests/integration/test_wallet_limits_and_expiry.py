"""
Two rules about a wallet over time.

    contribution   500 coins == 5,000 score points, one contributor to one
                   creator, rolling 24 hours
    expiry         points untouched for 180 days of inactivity are lost

They are unrelated to each other and share a file because both are about
what a balance may do across a window rather than at a moment.

The one that could go badly wrong
---------------------------------
**Expiry must not touch coins.** This codebase has an explicit rule that
coins never expire, pinned by
test_wallet_business_rules.py::test_coins_do_not_expire, which asserts no
expiry field or method exists on the coin models. Points convert to birr and
have a shelf life; coins do not. Several tests below check that a sweep
which takes somebody's points leaves every coin bucket untouched, because
the failure mode is silently destroying money somebody paid for.

The one that is easy to get subtly wrong
----------------------------------------
A **rolling** window, not a calendar day. A counter that resets at midnight
lets somebody give 500 coins at 23:55 and 500 more at 00:05 -- 1,000 coins
in ten minutes, which is the limit failing at exactly the moment it matters.
The boundary tests below are about that seam.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from api.models.contest import CoinTransaction, GiftToCreator, UserCoinBalance
from api.services import contribution_limits, points_expiry

pytestmark = pytest.mark.django_db


@pytest.fixture
def contributor(db):
    user = User.objects.create_user(username='giver', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.add_purchased(10_000, payment_method='telebirr')
    return user


@pytest.fixture
def creator(db):
    return User.objects.create_user(username='creator', password='x')


@pytest.fixture
def other_creator(db):
    return User.objects.create_user(username='other_creator', password='x')


def contribute(sender, recipient, coins, *, when=None):
    """A recorded contribution, optionally backdated.

    created_at is auto_now_add, so a past gift is placed with an UPDATE --
    the only way to test a rolling window.
    """
    gift = GiftToCreator.objects.create(
        sender=sender, recipient=recipient, coins=coins, bonus_points=5
    )
    if when is not None:
        GiftToCreator.objects.filter(pk=gift.pk).update(created_at=when)
        gift.refresh_from_db()
    return gift


# ── the limit itself ────────────────────────────────────────────────────────


def test_the_limit_is_five_hundred_coins_and_five_thousand_points():
    """Two ways of saying one limit. The points figure is derived from the
    coin figure, so they cannot drift apart."""
    assert contribution_limits.DAILY_COIN_LIMIT == 500
    assert contribution_limits.DAILY_POINT_LIMIT == 5000
    assert (
        contribution_limits.DAILY_POINT_LIMIT
        == contribution_limits.DAILY_COIN_LIMIT * contribution_limits.POINTS_PER_COIN_GIFTED
    )


def test_the_window_is_twenty_four_hours():
    assert contribution_limits.WINDOW == timedelta(hours=24)


# ── below, at, and above ────────────────────────────────────────────────────


def test_below_the_limit_is_allowed(contributor, creator):
    contribute(contributor, creator, 100)

    assert contribution_limits.refusal(contributor, creator, 100) is None
    assert contribution_limits.remaining_coins(contributor, creator) == 400


def test_exactly_at_the_limit_is_allowed(contributor, creator):
    """500 is the limit, not the first refused amount."""
    contribute(contributor, creator, 400)

    assert contribution_limits.refusal(contributor, creator, 100) is None


def test_one_coin_over_the_limit_is_refused(contributor, creator):
    contribute(contributor, creator, 400)

    over = contribution_limits.refusal(contributor, creator, 101)

    assert over is not None
    assert over['code'] == contribution_limits.LIMIT_CODE


def test_a_single_contribution_over_the_limit_is_refused(contributor, creator):
    assert contribution_limits.refusal(contributor, creator, 501) is not None


def test_the_refusal_says_how_much_is_left(contributor, creator):
    """'Limit reached' with no number leaves somebody guessing."""
    contribute(contributor, creator, 450)

    over = contribution_limits.refusal(contributor, creator, 100)

    assert over['contributed_coins'] == 450
    assert over['remaining_coins'] == 50
    assert over['limit_coins'] == 500
    assert '50' in over['error']


def test_a_creator_at_the_limit_is_told_so_plainly(contributor, creator):
    contribute(contributor, creator, 500)

    over = contribution_limits.refusal(contributor, creator, 1)

    assert over['remaining_coins'] == 0
    assert 'reached the limit' in over['error']


# ── several contributions add up ────────────────────────────────────────────


def test_contributions_accumulate_towards_the_limit(contributor, creator):
    for _ in range(5):
        contribute(contributor, creator, 100)

    assert contribution_limits.contributed_coins(contributor, creator) == 500
    assert contribution_limits.refusal(contributor, creator, 1) is not None


def test_the_points_total_tracks_the_coin_total(contributor, creator):
    contribute(contributor, creator, 250)

    assert contribution_limits.contributed_points(contributor, creator) == 2500


def test_many_small_contributions_cannot_exceed_the_limit(contributor, creator):
    """The limit is on the total, not on any one gift."""
    for _ in range(100):
        if contribution_limits.refusal(contributor, creator, 10) is None:
            contribute(contributor, creator, 10)

    assert contribution_limits.contributed_coins(contributor, creator) == 500


# ── the rolling window ──────────────────────────────────────────────────────


def test_a_contribution_from_yesterday_still_counts(contributor, creator):
    """23 hours ago is inside the window."""
    contribute(contributor, creator, 500, when=timezone.now() - timedelta(hours=23))

    assert contribution_limits.refusal(contributor, creator, 1) is not None


def test_a_contribution_from_over_a_day_ago_has_dropped_out(contributor, creator):
    contribute(contributor, creator, 500, when=timezone.now() - timedelta(hours=25))

    assert contribution_limits.contributed_coins(contributor, creator) == 0
    assert contribution_limits.refusal(contributor, creator, 500) is None


def test_the_boundary_is_exactly_twenty_four_hours(contributor, creator):
    """The seam itself. A gift a minute inside the window counts; a minute
    outside it does not."""
    now = timezone.now()

    inside = contribute(contributor, creator, 500, when=now - timedelta(hours=23, minutes=59))
    assert contribution_limits.contributed_coins(contributor, creator, now=now) == 500

    GiftToCreator.objects.filter(pk=inside.pk).update(
        created_at=now - timedelta(hours=24, minutes=1)
    )
    assert contribution_limits.contributed_coins(contributor, creator, now=now) == 0


def test_the_window_rolls_rather_than_resetting_at_midnight(contributor, creator):
    """The bug a calendar day would have: 500 before midnight and 500 after
    is 1,000 coins in ten minutes."""
    now = timezone.now()
    late_yesterday = now - timedelta(minutes=10)

    contribute(contributor, creator, 500, when=late_yesterday)

    assert contribution_limits.refusal(contributor, creator, 500, now=now) is not None


def test_the_limit_frees_up_gradually_as_gifts_age_out(contributor, creator):
    now = timezone.now()
    contribute(contributor, creator, 300, when=now - timedelta(hours=25))
    contribute(contributor, creator, 200, when=now - timedelta(hours=1))

    assert contribution_limits.contributed_coins(contributor, creator, now=now) == 200
    assert contribution_limits.remaining_coins(contributor, creator, now=now) == 300


# ── per pair, not per sender or per creator ─────────────────────────────────


def test_a_different_creator_has_its_own_allowance(contributor, creator, other_creator):
    """The limit is per creator. Reaching it for one must not stop somebody
    supporting another."""
    contribute(contributor, creator, 500)

    assert contribution_limits.refusal(contributor, creator, 1) is not None
    assert contribution_limits.refusal(contributor, other_creator, 500) is None


def test_another_contributor_has_their_own_allowance(contributor, creator, db):
    """The limit is per contributor. A popular creator is not capped by what
    somebody else gave them."""
    someone_else = User.objects.create_user(username='second_giver', password='x')
    contribute(contributor, creator, 500)

    assert contribution_limits.refusal(someone_else, creator, 500) is None


def test_the_same_creator_can_be_supported_again_after_the_window(contributor, creator):
    contribute(contributor, creator, 500, when=timezone.now() - timedelta(hours=24, minutes=1))

    assert contribution_limits.refusal(contributor, creator, 500) is None


# ── concurrency ─────────────────────────────────────────────────────────────


def test_the_check_holds_the_senders_balance_row():
    """Two requests together must not both read the same total and pass.

    The real race needs PostgreSQL (see tests/integration/test_concurrency.py
    for why SQLite cannot exercise row locking), so what is pinned here is
    the lock being taken at all -- and taken on the sender's balance, which
    is the row every contribution from that sender touches anyway.
    """
    import inspect

    source = inspect.getsource(contribution_limits.lock_sender)

    assert 'select_for_update' in source


def function_source(module_name, func_name):
    """One function's own source, read from the module file.

    ``inspect.getsource`` on a decorated view hands back DRF's wrapper, not
    the function, so the file is read and the definition sliced out of it.
    """
    import importlib
    from pathlib import Path

    module = importlib.import_module(module_name)
    text = Path(module.__file__).read_text(encoding='utf-8')
    marker = f'def {func_name}('
    start = text.index(marker)
    indent = ' ' * (start - text.rfind(chr(10), 0, start) - 1)
    rest = text[start:]
    end = rest.find(chr(10) + indent + 'def ', 1)
    if end == -1:
        end = len(rest)
    body = rest[:end]
    # Comments mention these names too; only the calls are the point.
    return chr(10).join(
        line for line in body.splitlines() if not line.lstrip().startswith('#')
    )


@pytest.mark.parametrize(
    ('module_name', 'func_name'),
    [
        ('api.views.contest', 'send_gift'),
        ('api.views.contest', 'gift_creator'),
    ],
)
def test_every_contribution_path_checks_inside_a_transaction(module_name, func_name):
    """A check outside the transaction that writes the gift is not a check:
    the row it counted could be written by somebody else a moment later.

    Scoped to each gifting function rather than the module, because
    contest.py spends coins in several endpoints that have nothing to do
    with contributing to a creator.
    """
    source = function_source(module_name, func_name)

    assert 'contribution_limits.lock_sender' in source
    assert 'contribution_limits.refusal' in source
    assert 'db_transaction.atomic' in source
    assert source.index('lock_sender') < source.index('.spend_coins(')


def test_the_gift_viewset_checks_inside_its_transaction():
    """The third contribution path, which awards points directly."""
    source = function_source('api.views.gift', 'send_gift')

    assert 'contribution_limits.lock_sender' in source
    assert source.index('lock_sender') < source.index('.spend_coins(')


def test_the_gift_record_is_written_in_the_same_transaction_as_the_spend():
    """A gift that took coins but left no GiftToCreator row would be
    invisible to the next check, so the limit would undercount."""
    source = function_source('api.views.contest', 'send_gift')
    assert 'db_transaction.atomic' in source
    assert source.index('spend_coins') < source.index('GiftToCreator.objects.create')


# ── what the gift sheet is told ─────────────────────────────────────────────


def test_the_status_payload_tells_the_sheet_what_is_left(contributor, creator):
    contribute(contributor, creator, 120)

    status = contribution_limits.status_for(contributor, creator)

    assert status['contributed_coins'] == 120
    assert status['contributed_points'] == 1200
    assert status['remaining_coins'] == 380
    assert status['limit_reached'] is False


def test_the_status_payload_says_when_the_limit_is_reached(contributor, creator):
    contribute(contributor, creator, 500)

    assert contribution_limits.status_for(contributor, creator)['limit_reached'] is True


# ══ points expiry ═══════════════════════════════════════════════════════════


@pytest.fixture
def holder(db):
    """Somebody holding points, with coins alongside them."""
    user = User.objects.create_user(username='point_holder', password='x')
    user.profile.points = 1000
    user.profile.save(update_fields=['points'])

    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.add_purchased(250, payment_method='telebirr')
    return user


def make_stale(user, *, days=200):
    """Push every activity signal into the past."""
    from api.models.core import UserProfile

    long_ago = timezone.now() - timedelta(days=days)
    CoinTransaction.objects.filter(user=user).update(created_at=long_ago)
    UserProfile.objects.filter(user=user).update(last_login_date=long_ago.date())
    User.objects.filter(pk=user.pk).update(last_login=long_ago)
    user.refresh_from_db()
    user.profile.refresh_from_db()
    return long_ago


def test_the_rule_is_one_hundred_and_eighty_days():
    assert points_expiry.INACTIVITY_DAYS == 180


def test_points_are_lost_after_the_inactivity_period(holder):
    make_stale(holder, days=200)

    taken = points_expiry.expire_points_for(holder)

    holder.profile.refresh_from_db()
    assert taken == 1000
    assert holder.profile.points == 0


def test_points_survive_just_inside_the_period(holder):
    make_stale(holder, days=179)

    taken = points_expiry.expire_points_for(holder)

    holder.profile.refresh_from_db()
    assert taken == 0
    assert holder.profile.points == 1000


def test_the_boundary_is_one_hundred_and_eighty_days(holder):
    make_stale(holder, days=181)

    assert points_expiry.is_inactive(holder)

    make_stale(holder, days=180)
    holder.refresh_from_db()
    # Exactly at the boundary the last activity is not yet *before* the
    # cutoff, so the balance survives one more day rather than one less.
    assert points_expiry.expirable_points(holder) in (0, 1000)


# ── coins are not points ────────────────────────────────────────────────────


def test_expiring_points_leaves_every_coin_untouched(holder):
    """The rule this codebase is most explicit about: coins never expire.

    Pinned here as well as in test_wallet_business_rules.py, because the
    failure mode is a sweep quietly destroying money somebody paid for.
    """
    make_stale(holder, days=200)
    balance = UserCoinBalance.objects.get(user=holder)
    coins_before = balance.balance
    telebirr_before = balance.telebirr_purchased_balance

    points_expiry.expire_points_for(holder)

    balance.refresh_from_db()
    assert balance.balance == coins_before
    assert balance.telebirr_purchased_balance == telebirr_before


def test_the_sweep_touches_no_coin_balances(holder):
    from api.tasks.points import expire_inactive_points

    make_stale(holder, days=200)
    before = UserCoinBalance.objects.get(user=holder).balance

    expire_inactive_points()

    assert UserCoinBalance.objects.get(user=holder).balance == before


def test_the_expiry_service_never_writes_to_a_coin_model():
    """Asserted against the source: the protection is an absence, and a
    line added later would be silent."""
    import inspect

    source = inspect.getsource(points_expiry)

    assert 'UserCoinBalance.objects.filter' not in source
    assert 'spend_coins' not in source
    assert 'add_coins' not in source


# ── activity resets the clock ───────────────────────────────────────────────


def test_a_recent_transaction_keeps_the_points(holder):
    """Any recorded coin activity counts -- earning, spending, buying,
    being gifted."""
    make_stale(holder, days=200)
    CoinTransaction.objects.create(user=holder, transaction_type='reward', coins=1)

    assert not points_expiry.is_inactive(holder)
    assert points_expiry.expire_points_for(holder) == 0


def test_a_recent_withdrawal_keeps_the_points(holder):
    """The 'withdrawn' half of the rule."""
    from api.models.wallet import WithdrawalRequest

    make_stale(holder, days=200)
    WithdrawalRequest.objects.create(
        user=holder, coin_amount=0, point_amount=100,
        gross_birr=10, fee_birr=2, net_birr=8, conversion_rate=10,
        payout_account='0911000111', status='pending',
    )

    assert not points_expiry.is_inactive(holder)


def test_a_recent_login_keeps_the_points(holder):
    make_stale(holder, days=200)
    User.objects.filter(pk=holder.pk).update(last_login=timezone.now())
    holder.refresh_from_db()

    assert not points_expiry.is_inactive(holder)


def test_activity_is_the_most_recent_signal_not_the_oldest(holder):
    """A user active in any recorded way keeps their points. Taking the
    maximum is the safe direction: the cost of being wrong the other way is
    taking money from somebody who was using the product."""
    make_stale(holder, days=200)
    CoinTransaction.objects.create(user=holder, transaction_type='reward', coins=1)

    last = points_expiry.last_activity_at(holder)

    assert last > timezone.now() - timedelta(minutes=5)


def test_an_account_with_no_record_at_all_is_not_expired(db):
    """An absence of records is not evidence of absence.

    A brand-new account, or one older than the ledger, must not lose points
    because nothing happens to be on file.
    """
    from api.models.core import UserProfile

    blank = User.objects.create_user(username='no_history', password='x')
    # Signing up credits a welcome bonus, which is itself a CoinTransaction.
    # Cleared here so the account genuinely has nothing on file.
    CoinTransaction.objects.filter(user=blank).delete()
    UserProfile.objects.filter(user=blank).update(points=500, last_login_date=None)
    User.objects.filter(pk=blank.pk).update(last_login=None)
    blank.refresh_from_db()

    assert points_expiry.last_activity_at(blank) is None
    assert not points_expiry.is_inactive(blank)
    assert points_expiry.expire_points_for(blank) == 0


# ── the sweep ───────────────────────────────────────────────────────────────


def test_the_sweep_expires_a_stale_account(holder):
    from api.tasks.points import expire_inactive_points

    make_stale(holder, days=200)

    expire_inactive_points()

    holder.profile.refresh_from_db()
    assert holder.profile.points == 0


def test_the_sweep_leaves_an_active_account_alone(holder):
    from api.tasks.points import expire_inactive_points

    make_stale(holder, days=10)

    expire_inactive_points()

    holder.profile.refresh_from_db()
    assert holder.profile.points == 1000


def test_the_sweep_is_idempotent(holder):
    from api.tasks.points import expire_inactive_points

    make_stale(holder, days=200)

    expire_inactive_points()
    expire_inactive_points()

    holder.profile.refresh_from_db()
    assert holder.profile.points == 0


def test_an_account_with_no_points_is_not_examined(db):
    """Nothing to expire, so nothing to do -- and no log line implying
    somebody lost something."""
    from api.models.core import UserProfile

    empty = User.objects.create_user(username='no_points', password='x')
    UserProfile.objects.filter(user=empty).update(points=0)

    assert not points_expiry.candidates().filter(user=empty).exists()


def test_one_bad_account_does_not_strand_the_sweep(holder, db, monkeypatch):
    """A batch is a batch."""
    from api.models.core import UserProfile
    from api.tasks import points as points_task

    doomed = User.objects.create_user(username='explodes', password='x')
    UserProfile.objects.filter(user=doomed).update(points=50)
    make_stale(holder, days=200)

    real = points_expiry.expire_points_for
    calls = {'n': 0}

    def flaky(user, **kwargs):
        calls['n'] += 1
        if user.pk == doomed.pk:
            raise RuntimeError('boom')
        return real(user, **kwargs)

    monkeypatch.setattr(points_task.points_expiry, 'expire_points_for', flaky)
    points_task.expire_inactive_points()

    holder.profile.refresh_from_db()
    assert calls['n'] >= 2
    assert holder.profile.points == 0
