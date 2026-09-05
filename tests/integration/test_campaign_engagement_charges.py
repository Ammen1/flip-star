"""
Coin deduction for campaign engagement: post, like, comment, share.

Why deductions were not happening
---------------------------------
Every cost on WalletConfig defaults to 0, and each call site guards with
``if cost > 0``. On staging all nine were 0, so nothing was ever charged --
the feature was switched off, not broken. These tests therefore configure a
price explicitly rather than relying on defaults, which is also what stops a
future default change from silently making them pass for the wrong reason.

The defects that mattered once a price is set:

  post      api/views/campaign_user.py:create_campaign_post charged nothing at
            all, while core.py:create_post charged for the same act -- so the
            price depended on which endpoint a client called
  comment    the charge ran BEFORE Comment.objects.create() and outside any
            transaction, so a failure between them billed for nothing
  share      no idempotency of any kind: every double-tap, retry and refresh
            deducted again
  counters   `reel.votes += 1; reel.save()` is read-modify-write, so
            concurrent requests lose increments

Like was already safe, by accident: get_or_create meant the charge only ran
for a genuinely new vote.
"""

import pytest
from django.contrib.auth.models import User
from django.db import transaction

from api.models import Reel, Vote
from api.models.contest import CoinTransaction, UserCoinBalance
from api.models.wallet import WalletConfig
from api.services.campaign_charges import (
    InsufficientCoins,
    already_charged,
    charge_engagement,
    engagement_cost,
)

pytestmark = pytest.mark.django_db

LIKE_COST = 5
COMMENT_COST = 7
SHARE_COST = 3
POST_COST = 20


@pytest.fixture
def priced():
    """A config with every engagement priced, so 0 cannot mask a failure."""
    config = WalletConfig.get_config()
    config.cost_like = LIKE_COST
    config.cost_comment = COMMENT_COST
    config.cost_share = SHARE_COST
    config.cost_post_create = POST_COST
    config.cost_like_non_campaign = 0
    config.cost_comment_non_campaign = 0
    config.cost_share_non_campaign = 0
    config.cost_post_create_non_campaign = 0
    config.save()
    WalletConfig.get_config.cache_clear() if hasattr(
        WalletConfig.get_config, 'cache_clear'
    ) else None
    return config


@pytest.fixture
def author():
    return User.objects.create_user(username='campaign_author', password='x')


@pytest.fixture
def actor():
    user = User.objects.create_user(username='engager', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.add_earned(1000, 'admin_adjustment')
    return user


@pytest.fixture
def campaign_reel(author):
    return Reel.objects.create(user=author, caption='entry', is_campaign_post=True)


@pytest.fixture
def ordinary_reel(author):
    return Reel.objects.create(user=author, caption='just a post', is_campaign_post=False)


def balance_of(user):
    return UserCoinBalance.objects.get(user=user).balance


def broke(username):
    """A user with genuinely nothing.

    api/signals.py grants a welcome bonus when a user is created, so a fresh
    account starts with a balance -- zeroing it explicitly is what makes these
    tests about insufficiency rather than about the size of that bonus.
    """
    user = User.objects.create_user(username=username, password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        earned_balance=0,
        airtime_purchased_balance=0,
        telebirr_purchased_balance=0,
        purchased_balance=0,
        balance=0,
    )
    return user


# ---------------------------------------------------------------------------
# Pricing comes from configuration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('action', 'expected'),
    [('like', LIKE_COST), ('comment', COMMENT_COST), ('share', SHARE_COST), ('post', POST_COST)],
)
def test_cost_is_read_from_wallet_config(priced, campaign_reel, action, expected):
    assert engagement_cost(campaign_reel, action) == expected


@pytest.mark.parametrize('action', ['like', 'comment', 'share', 'post'])
def test_ordinary_posts_use_their_own_prices(priced, ordinary_reel, action):
    """Campaign and non-campaign engagement are priced separately."""
    assert engagement_cost(ordinary_reel, action) == 0


@pytest.mark.parametrize('action', ['like', 'comment', 'share', 'post'])
def test_zero_cost_charges_nothing(campaign_reel, actor, action):
    """
    A cost of 0 is the documented way to disable charging, not a bug.

    This is the state staging was actually in, which is why no deduction was
    happening anywhere.
    """
    config = WalletConfig.get_config()
    setattr(config, f'cost_{"post_create" if action == "post" else action}', 0)
    config.save()

    before = balance_of(actor)
    assert charge_engagement(actor, campaign_reel, action) == 0
    assert balance_of(actor) == before


def test_unknown_action_is_rejected(campaign_reel):
    with pytest.raises(ValueError, match='Unknown engagement action'):
        engagement_cost(campaign_reel, 'teleport')


# ---------------------------------------------------------------------------
# The four flows deduct
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('action', 'cost'),
    [('like', LIKE_COST), ('comment', COMMENT_COST), ('share', SHARE_COST), ('post', POST_COST)],
)
def test_each_action_deducts_the_configured_amount(priced, campaign_reel, actor, action, cost):
    before = balance_of(actor)

    assert charge_engagement(actor, campaign_reel, action) == cost

    assert balance_of(actor) == before - cost


@pytest.mark.parametrize('action', ['like', 'comment', 'share', 'post'])
def test_every_deduction_writes_an_audit_record(priced, campaign_reel, actor, action):
    """Balance has to be reconstructible from the ledger."""
    charge_engagement(actor, campaign_reel, action)

    tx = CoinTransaction.objects.filter(user=actor, reel=campaign_reel).latest('created_at')
    assert tx.is_successful
    assert tx.coins != 0
    assert tx.description


# ---------------------------------------------------------------------------
# Who is not charged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('action', ['like', 'comment', 'share'])
def test_the_author_is_never_charged_on_their_own_post(priced, campaign_reel, author, action):
    UserCoinBalance.objects.get_or_create(user=author)
    before = balance_of(author)

    assert charge_engagement(author, campaign_reel, action) == 0
    assert balance_of(author) == before


def test_an_anonymous_request_is_not_charged(priced, campaign_reel):
    class Anon:
        is_authenticated = False
        id = None

    assert charge_engagement(Anon(), campaign_reel, 'share') == 0


# ---------------------------------------------------------------------------
# Insufficient balance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('action', ['like', 'comment', 'share', 'post'])
def test_insufficient_balance_raises_with_the_numbers(priced, campaign_reel, action):
    poor = broke(f'poor_{action}')

    with pytest.raises(InsufficientCoins) as exc:
        charge_engagement(poor, campaign_reel, action)

    assert exc.value.required > 0
    assert exc.value.available == 0
    assert exc.value.message


def test_a_refused_charge_takes_nothing(priced, campaign_reel):
    poor = broke('poor_partial')
    UserCoinBalance.objects.get(user=poor).add_earned(LIKE_COST - 1, 'admin_adjustment')
    before = balance_of(poor)

    with pytest.raises(InsufficientCoins):
        charge_engagement(poor, campaign_reel, 'like')

    assert balance_of(poor) == before, 'a partial deduction was taken'


# ---------------------------------------------------------------------------
# Duplicate protection
# ---------------------------------------------------------------------------


def test_share_charges_once_however_many_times_it_is_called(priced, campaign_reel, actor):
    """
    The double-charge case.

    Share has no uniqueness constraint of its own, so before `once=True` a
    double-tap, a retry and a refresh each deducted again.
    """
    before = balance_of(actor)

    first = charge_engagement(actor, campaign_reel, 'share', once=True)
    repeats = [charge_engagement(actor, campaign_reel, 'share', once=True) for _ in range(4)]

    assert first == SHARE_COST
    assert repeats == [0, 0, 0, 0]
    assert balance_of(actor) == before - SHARE_COST


def test_a_repeat_is_free_rather_than_an_error(priced, campaign_reel, actor):
    """
    The action did happen from the user's point of view -- they simply are not
    billed twice. Raising here would surface a failure for a share that
    succeeded.
    """
    charge_engagement(actor, campaign_reel, 'share', once=True)

    assert charge_engagement(actor, campaign_reel, 'share', once=True) == 0


def test_once_is_scoped_to_the_reel(priced, actor, author):
    """Paying to share one post must not make every other share free."""
    a = Reel.objects.create(user=author, caption='a', is_campaign_post=True)
    b = Reel.objects.create(user=author, caption='b', is_campaign_post=True)

    assert charge_engagement(actor, a, 'share', once=True) == SHARE_COST
    assert charge_engagement(actor, b, 'share', once=True) == SHARE_COST


def test_once_is_scoped_to_the_user(priced, campaign_reel, actor):
    other = User.objects.create_user(username='other_sharer', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=other)
    balance.add_earned(100, 'admin_adjustment')

    charge_engagement(actor, campaign_reel, 'share', once=True)

    assert charge_engagement(other, campaign_reel, 'share', once=True) == SHARE_COST


def test_already_charged_reflects_the_ledger(priced, campaign_reel, actor):
    assert already_charged(actor, campaign_reel, 'share') is False

    charge_engagement(actor, campaign_reel, 'share', once=True)

    assert already_charged(actor, campaign_reel, 'share') is True
    # A different action on the same reel is a separate charge.
    assert already_charged(actor, campaign_reel, 'comment') is False


def test_like_is_naturally_idempotent(priced, campaign_reel, actor):
    """get_or_create means the charge only runs for a genuinely new vote."""
    before = balance_of(actor)

    for _ in range(3):
        vote, created = Vote.objects.get_or_create(user=actor, reel=campaign_reel)
        if created:
            charge_engagement(actor, campaign_reel, 'like')

    assert balance_of(actor) == before - LIKE_COST
    assert Vote.objects.filter(user=actor, reel=campaign_reel).count() == 1


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------


def test_a_failure_after_the_charge_rolls_the_charge_back(priced, campaign_reel, actor):
    """
    The guarantee the ordering exists to provide.

    spend_coins opens its own atomic block, which nests as a savepoint inside
    the caller's -- so an exception in the enclosing block undoes the balance
    write too, rather than leaving it committed.
    """
    before = balance_of(actor)

    with pytest.raises(RuntimeError), transaction.atomic():
        charge_engagement(actor, campaign_reel, 'like')
        raise RuntimeError('the action failed after the charge')

    assert balance_of(actor) == before, 'charge survived a rolled-back action'


def test_a_rolled_back_charge_leaves_no_ledger_entry(priced, campaign_reel, actor):
    """The audit trail must not record a deduction that did not happen."""
    with pytest.raises(RuntimeError), transaction.atomic():
        charge_engagement(actor, campaign_reel, 'comment')
        raise RuntimeError('boom')

    assert not CoinTransaction.objects.filter(
        user=actor, reel=campaign_reel, transaction_type='campaign_comment'
    ).exists()


def test_a_rolled_back_charge_does_not_count_as_already_charged(priced, campaign_reel, actor):
    """Otherwise a failed attempt would make the retry free."""
    with pytest.raises(RuntimeError), transaction.atomic():
        charge_engagement(actor, campaign_reel, 'share', once=True)
        raise RuntimeError('boom')

    assert already_charged(actor, campaign_reel, 'share') is False
    assert charge_engagement(actor, campaign_reel, 'share', once=True) == SHARE_COST


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


def test_counters_use_f_expressions_not_read_modify_write():
    """
    `reel.votes += 1; reel.save()` loses an increment when two requests
    interleave. Asserted against the source because the race needs real
    concurrency to reproduce, which SQLite cannot provide.
    """
    from pathlib import Path

    import api.views.core as core_module

    # Comments stripped first: the fix documents itself by quoting the very
    # pattern this asserts is gone, which would fail on its own explanation.
    src = chr(10).join(
        line
        for line in Path(core_module.__file__).read_text(encoding='utf-8').splitlines()
        if not line.lstrip().startswith('#')
    )

    assert 'reel.votes += 1' not in src, 'like still uses read-modify-write'
    assert 'reel.shares += 1' not in src, 'share still uses read-modify-write'
    assert "update(votes=F('votes') + 1)" in src
    assert "update(shares=F('shares') + 1)" in src


# ---------------------------------------------------------------------------
# Both post endpoints charge
# ---------------------------------------------------------------------------


def test_the_campaign_post_endpoint_charges():
    """
    create_campaign_post used to charge nothing, while core.py:create_post
    charged for the same act -- so the price depended on which endpoint a
    client happened to call.
    """
    from pathlib import Path

    import api.views.campaign_user as module

    src = Path(module.__file__).read_text(encoding='utf-8')

    assert 'charge_engagement' in src, 'campaign post endpoint still charges nothing'
    assert 'InsufficientCoins' in src, 'no refusal path for an unaffordable entry'


# ---------------------------------------------------------------------------
# Lock ordering
# ---------------------------------------------------------------------------


def test_the_ledger_check_happens_under_the_balance_lock():
    """
    The subtle version of the double-charge bug.

    `once` first checked the ledger and only then called spend_coins, which
    takes the row lock. Two simultaneous shares therefore both found no prior
    transaction, both proceeded, and the user was charged twice -- the exact
    failure `once` exists to prevent, reintroduced one layer down.

    Asserted against the source: SELECT ... FOR UPDATE has no meaningful
    semantics on SQLite, which is why tests/integration/test_concurrency.py
    skips its locking tests unless a real PostgreSQL is configured. This at
    least pins the ordering so it cannot be silently reversed.
    """
    from pathlib import Path

    import api.services.campaign_charges as module

    src = Path(module.__file__).read_text(encoding='utf-8')
    body = src.split('def charge_engagement')[1].split(chr(10) + 'def ')[0]

    lock_at = body.find('select_for_update')
    check_at = body.find('already_charged')

    assert lock_at != -1, 'the balance row is never locked'
    assert check_at != -1, 'the ledger is never consulted'
    assert lock_at < check_at, (
        'already_charged() runs before select_for_update(), so two concurrent '
        'requests can both pass the check and both charge'
    )
