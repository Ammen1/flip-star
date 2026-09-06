"""
Subscription bonus coins are a separate bucket, and they cannot pay for gifts.

Why a bucket and not a flag
---------------------------
The restriction has to be enforceable at the moment coins are spent. A flag on
the transaction log would mean replaying history to answer "how many of these
coins may fund a gift?"; a bucket answers it from the balance itself, under the
same row lock that already prevents overspending.

The rule
--------
A gift moves value to another user, who can gift it onward or withdraw it. So a
gift may only be paid for with coins the sender actually bought -- never with a
reward, never with a subscription perk, never with airtime credit. Exactly one
bucket qualifies, and `giftable_balance` names it.

The bug this also closes
------------------------
The gift endpoint checked `purchased_balance` (Telebirr + airtime) while
`spend_coins(restrict_earned=True)` accepts Telebirr alone. A user holding only
airtime coins therefore passed the endpoint's check and hit a raw ValueError
from inside the spend. Both now read `giftable_balance`.
"""

import pytest
from django.contrib.auth.models import User

from api.models.contest import UserCoinBalance

pytestmark = pytest.mark.django_db


@pytest.fixture
def wallet():
    """A wallet with every bucket at zero.

    Written directly rather than through the credit helpers because
    api/signals.py grants a welcome bonus on user creation, which would
    otherwise leave a balance the assertions did not ask for.
    """
    user = User.objects.create_user(username='giver', password='123456')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        earned_balance=0,
        bonus_balance=0,
        telebirr_purchased_balance=0,
        airtime_purchased_balance=0,
        purchased_balance=0,
        balance=0,
    )
    balance.refresh_from_db()
    return balance


def fund(balance, *, purchased=0, bonus=0, earned=0, airtime=0):
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        telebirr_purchased_balance=purchased,
        bonus_balance=bonus,
        earned_balance=earned,
        airtime_purchased_balance=airtime,
        purchased_balance=purchased + airtime,
        balance=purchased + bonus + earned + airtime,
    )
    balance.refresh_from_db()
    return balance


# ---------------------------------------------------------------------------
# The buckets stay separate
# ---------------------------------------------------------------------------


def test_bonus_coins_are_tracked_in_their_own_bucket(wallet):
    wallet.add_bonus(500, description='Premium subscription')

    wallet.refresh_from_db()
    assert wallet.bonus_balance == 500
    assert wallet.total_bonus_granted == 500


def test_bonus_coins_are_not_counted_as_purchased(wallet):
    """
    The separation that matters.

    Folding bonus coins into `purchased_balance` would make them look
    spendable everywhere purchased coins are -- including the gift endpoint,
    which is the one place they must not be.
    """
    wallet.add_bonus(500)

    wallet.refresh_from_db()
    assert wallet.purchased_balance == 0
    assert wallet.giftable_balance == 0


def test_bonus_coins_do_count_towards_the_total(wallet):
    """The user does hold them, and the wallet should say so."""
    wallet.add_bonus(500)

    wallet.refresh_from_db()
    assert wallet.balance == 500


def test_purchased_and_bonus_coexist_without_mixing(wallet):
    fund(wallet, purchased=100, bonus=500)

    assert wallet.giftable_balance == 100
    assert wallet.bonus_balance == 500
    assert wallet.balance == 600


# ---------------------------------------------------------------------------
# Gifting
# ---------------------------------------------------------------------------


def test_a_gift_cannot_be_paid_for_with_bonus_coins_alone(wallet):
    """
    The worked example: 0 purchased, 500 bonus, gift costs 50.

    Rejected, and nothing is deducted.
    """
    fund(wallet, purchased=0, bonus=500)

    with pytest.raises(ValueError) as exc:
        wallet.spend_coins(50, 'gift_sent', restrict_earned=True)

    wallet.refresh_from_db()
    assert wallet.bonus_balance == 500, 'bonus coins were taken for a gift'
    assert wallet.balance == 500
    assert 'bonus' in str(exc.value).lower()


def test_the_refusal_names_bonus_coins_as_the_reason(wallet):
    """
    A user holding 500 coins and told "insufficient" would assume a bug.

    The message has to say which coins cannot pay and what can.
    """
    fund(wallet, purchased=0, bonus=500)

    with pytest.raises(ValueError) as exc:
        wallet.spend_coins(50, 'gift_sent', restrict_earned=True)

    message = str(exc.value)
    assert 'cannot be used to send gifts' in message
    assert 'purchased coins' in message.lower()


def test_a_gift_spends_purchased_coins_and_leaves_bonus_untouched(wallet):
    """100 purchased, 500 bonus, gift costs 50 -> 50 purchased remain, 500 bonus."""
    fund(wallet, purchased=100, bonus=500)

    wallet.spend_coins(50, 'gift_sent', restrict_earned=True)

    wallet.refresh_from_db()
    assert wallet.telebirr_purchased_balance == 50
    assert wallet.bonus_balance == 500, 'bonus coins were drawn into a gift'


def test_bonus_coins_never_top_up_a_short_purchased_balance(wallet):
    """
    20 purchased, 500 bonus, gift costs 50.

    The 30-coin shortfall must not be covered from bonus. Partial funding
    would be the same violation as full funding, just harder to notice.
    """
    fund(wallet, purchased=20, bonus=500)

    with pytest.raises(ValueError):
        wallet.spend_coins(50, 'gift_sent', restrict_earned=True)

    wallet.refresh_from_db()
    assert wallet.telebirr_purchased_balance == 20
    assert wallet.bonus_balance == 500


def test_earned_coins_still_cannot_fund_a_gift(wallet):
    """The pre-existing restriction, unchanged by the new bucket."""
    fund(wallet, purchased=0, earned=500)

    with pytest.raises(ValueError):
        wallet.spend_coins(50, 'gift_sent', restrict_earned=True)

    wallet.refresh_from_db()
    assert wallet.earned_balance == 500


def test_airtime_coins_still_cannot_fund_a_gift(wallet):
    fund(wallet, purchased=0, airtime=500)

    with pytest.raises(ValueError):
        wallet.spend_coins(50, 'gift_sent', restrict_earned=True)

    wallet.refresh_from_db()
    assert wallet.airtime_purchased_balance == 500


def test_giftable_balance_is_exactly_the_telebirr_bucket(wallet):
    """
    One definition, so the endpoint's pre-check and the spend cannot disagree.

    They did: the endpoint tested `purchased_balance`, which includes airtime.
    """
    fund(wallet, purchased=100, bonus=500, earned=200, airtime=300)

    assert wallet.giftable_balance == 100
    assert wallet.non_giftable_balance == 1000
    assert wallet.balance == 1100


# ---------------------------------------------------------------------------
# Bonus coins remain useful for everything else
# ---------------------------------------------------------------------------


def test_bonus_coins_can_pay_for_ordinary_actions(wallet):
    """
    The perk still works.

    Only gifting is restricted; a bonus coin spends like any other on boosts,
    campaign entry fees and engagement charges.
    """
    fund(wallet, bonus=500)

    wallet.spend_coins(50, 'boost')

    wallet.refresh_from_db()
    assert wallet.bonus_balance == 450
    assert wallet.balance == 450


def test_bonus_coins_are_spent_before_purchased_ones(wallet):
    """
    Cheapest outcome for the user.

    Bonus coins are a perk a lapsing subscription may withdraw, so they are
    drawn down before coins the user paid money for -- which are also the only
    ones that could have funded a gift.
    """
    fund(wallet, purchased=100, bonus=100)

    wallet.spend_coins(60, 'boost')

    wallet.refresh_from_db()
    assert wallet.bonus_balance == 40
    assert wallet.telebirr_purchased_balance == 100, 'purchased coins spent before bonus'


def test_a_large_spend_falls_through_the_buckets_in_order(wallet):
    fund(wallet, purchased=100, bonus=50, earned=30, airtime=20)

    wallet.spend_coins(120, 'boost')

    wallet.refresh_from_db()
    assert wallet.bonus_balance == 0
    assert wallet.earned_balance == 0
    assert wallet.airtime_purchased_balance == 0
    assert wallet.telebirr_purchased_balance == 80
    assert wallet.balance == 80


def test_an_unaffordable_ordinary_spend_changes_nothing(wallet):
    fund(wallet, purchased=10, bonus=10)

    with pytest.raises(ValueError):
        wallet.spend_coins(100, 'boost')

    wallet.refresh_from_db()
    assert wallet.bonus_balance == 10
    assert wallet.telebirr_purchased_balance == 10


# ---------------------------------------------------------------------------
# Bookkeeping
# ---------------------------------------------------------------------------


def test_granting_bonus_coins_records_a_transaction(wallet):
    from api.models.contest import CoinTransaction

    wallet.add_bonus(500, description='Premium subscription bonus')

    tx = CoinTransaction.objects.filter(user=wallet.user).order_by('-id').first()
    assert tx is not None
    assert tx.coins == 500


def test_a_negative_bonus_grant_is_refused(wallet):
    with pytest.raises(ValueError):
        wallet.add_bonus(-10)

    wallet.refresh_from_db()
    assert wallet.bonus_balance == 0


def test_the_in_memory_object_reflects_the_spend(wallet):
    """
    _copy_from must carry the new bucket.

    Views build their response body from this object after the call; a stale
    bonus_balance would report the pre-spend figure back to the user.
    """
    fund(wallet, bonus=100)

    wallet.spend_coins(40, 'boost')

    assert wallet.bonus_balance == 60, 'stale in-memory balance after spend'
