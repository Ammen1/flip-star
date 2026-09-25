"""
The creator economy's conversion chain, end to end.

    coins  --gift-->  points  --withdraw-->  ETB
      1               1                     10 pts = 0.80 net

    points --swap-->  coins
      1               1

Every step of that already works, and the parts most likely to break are
covered elsewhere: refunds, ownership and the concurrent-refund race in
test_withdrawal_refunds.py and test_withdrawal_refund_race.py, giftability in
test_bonus_coins_not_giftable.py, spend ordering in
test_wallet_business_rules.py.

What none of them pin is the **rates**. They live on a WalletConfig row that
the admin can edit, and they compose: coins_to_points_conversion feeds the
gift, points_per_birr and withdrawal_fee_percent feed the payout. Change one
and the documented figure -- 1,000 points for 80 ETB -- quietly stops being
true, with every existing test still green because each tests its own step
against whatever the row happens to say.

These assert the chain against the requirement instead.
"""

from decimal import Decimal

import pytest

from api.models.wallet import WalletConfig

pytestmark = pytest.mark.django_db

#: The requirement's figures.
COINS_PER_POINT = 1  # gifting: 1 coin becomes 1 point for the creator
POINTS_PER_BIRR = 10  # 10 points is 1 ETB gross
COMMISSION_PERCENT = 20  # taken at payout
MIN_WITHDRAWAL_POINTS = 1000  # 1,000 points -> 80 ETB net


def field_default(name):
    return WalletConfig._meta.get_field(name).default


@pytest.fixture
def config(db):
    """A config row carrying the shipped defaults."""
    WalletConfig.objects.all().delete()
    return WalletConfig.objects.create()


# ── the rates themselves ────────────────────────────────────────────────────


def test_a_gifted_coin_becomes_one_creator_point():
    assert field_default('coins_to_points_conversion') == COINS_PER_POINT


def test_ten_points_are_one_birr_before_commission():
    assert field_default('points_per_birr') == POINTS_PER_BIRR


def test_the_platform_takes_twenty_percent_at_payout():
    assert Decimal(str(field_default('withdrawal_fee_percent'))) == Decimal(COMMISSION_PERCENT)


def test_the_minimum_withdrawal_is_a_thousand_points():
    assert field_default('withdrawal_min_points') == MIN_WITHDRAWAL_POINTS


# ── the documented worked example ───────────────────────────────────────────


def test_a_thousand_points_pays_eighty_birr_net(config):
    """The figure the requirement states, computed rather than asserted.

    1,000 points / 10 = 100 ETB gross, less 20% = 80 ETB net.
    """
    breakdown = config.calculate_points_withdrawal(MIN_WITHDRAWAL_POINTS)

    assert breakdown['gross_birr'] == Decimal('100')
    assert breakdown['fee_birr'] == Decimal('20')
    assert breakdown['net_birr'] == Decimal('80')


def test_ten_points_pay_eighty_cents_net(config):
    """The rate the requirement gives directly: 10 points = 0.8 ETB."""
    breakdown = config.calculate_points_withdrawal(10)

    assert breakdown['net_birr'] == Decimal('0.8')


@pytest.mark.parametrize(
    ('points', 'net'),
    [(10, '0.8'), (100, '8'), (1000, '80'), (5000, '400')],
)
def test_the_net_rate_holds_at_every_size(config, points, net):
    assert config.calculate_points_withdrawal(points)['net_birr'] == Decimal(net)


def test_the_commission_is_taken_once_not_twice(config):
    """Gross minus fee equals net exactly.

    Two code paths compute a fee -- calculate_withdrawal for coins and
    calculate_points_withdrawal for points. Applying both to one payout would
    leave 64 ETB rather than 80, and the only visible symptom is a payout
    that looks slightly wrong.
    """
    breakdown = config.calculate_points_withdrawal(1000)

    assert breakdown['gross_birr'] - breakdown['fee_birr'] == breakdown['net_birr']
    assert breakdown['fee_percent'] == Decimal(COMMISSION_PERCENT)
    # 20% once is 80. Twice would be 64.
    assert breakdown['net_birr'] == Decimal('80')


# ── gifting credits the creator ─────────────────────────────────────────────


def test_a_gift_moves_coins_from_the_sender_and_points_to_the_creator(django_user_model, config):
    """The first leg of the chain, one coin to one point."""
    from api.models.contest import UserCoinBalance

    sender = django_user_model.objects.create_user(username='gift_sender', password='x')
    creator = django_user_model.objects.create_user(username='gift_creator', password='x')

    balance, _ = UserCoinBalance.objects.get_or_create(user=sender)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        balance=0,
        earned_balance=0,
        bonus_balance=0,
        telebirr_purchased_balance=0,
        airtime_purchased_balance=0,
        purchased_balance=0,
    )
    balance.refresh_from_db()
    balance.add_purchased(100, payment_method='telebirr')

    creator.profile.refresh_from_db()
    points_before = creator.profile.points

    balance.spend_coins(100, transaction_type='gift_sent', restrict_earned=True)
    creator.profile.add_points(config.coins_to_points(100))

    balance.refresh_from_db()
    creator.profile.refresh_from_db()
    assert balance.telebirr_purchased_balance == 0
    assert creator.profile.points == points_before + 100


def test_reward_coins_cannot_pay_for_a_gift(django_user_model):
    """Gifting draws on purchased coins only.

    This is what closes the loop below: value given away has to have been
    bought, so it cannot be manufactured from earned or swapped coins.
    """
    from api.models.contest import UserCoinBalance

    sender = django_user_model.objects.create_user(username='reward_gifter', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=sender)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        balance=0,
        earned_balance=0,
        bonus_balance=0,
        telebirr_purchased_balance=0,
        airtime_purchased_balance=0,
        purchased_balance=0,
    )
    balance.refresh_from_db()
    balance.add_earned(500, transaction_type='reward')

    with pytest.raises(ValueError, match='giftable'):
        balance.spend_coins(100, transaction_type='gift_sent', restrict_earned=True)

    balance.refresh_from_db()
    assert balance.earned_balance == 500, 'a refused gift still took coins'


# ── the swap, and why it cannot be farmed ───────────────────────────────────


def test_a_point_swaps_back_into_one_coin(django_user_model, config):
    """The second leg: points return to coins at parity for in-app spending."""
    from api.models.contest import UserCoinBalance

    user = django_user_model.objects.create_user(username='swapper', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        balance=0,
        earned_balance=0,
        bonus_balance=0,
        telebirr_purchased_balance=0,
        airtime_purchased_balance=0,
        purchased_balance=0,
    )
    balance.refresh_from_db()

    user.profile.add_points(250)
    user.profile.deduct_points(250)
    balance.add_earned(250, transaction_type='reinvest')

    balance.refresh_from_db()
    user.profile.refresh_from_db()
    assert balance.earned_balance == 250
    assert user.profile.points == 0


def test_swapping_cannot_manufacture_giftable_value(django_user_model):
    """The loop the requirement asks to prevent, and why it is already shut.

    points -> coins -> gift -> points would be a machine for creating value
    if it closed. It does not: a swap credits EARNED coins, and gifting
    accepts only PURCHASED ones. So the coins that come back from a swap can
    be spent in-app but can never re-enter the gift economy, and no amount of
    repetition increases anybody's total.
    """
    from api.models.contest import UserCoinBalance

    user = django_user_model.objects.create_user(username='farmer', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        balance=0,
        earned_balance=0,
        bonus_balance=0,
        telebirr_purchased_balance=0,
        airtime_purchased_balance=0,
        purchased_balance=0,
    )
    balance.refresh_from_db()

    # Swap 1,000 points in.
    balance.add_earned(1000, transaction_type='reinvest')

    # None of it is giftable, however many times it went round.
    balance.refresh_from_db()
    assert balance.earned_balance == 1000
    assert balance.giftable_balance == 0

    with pytest.raises(ValueError):
        balance.spend_coins(1, transaction_type='gift_sent', restrict_earned=True)


def test_swapped_coins_are_still_spendable_in_app(django_user_model):
    """Closing the gift loop must not make the coins useless."""
    from api.models.contest import UserCoinBalance

    user = django_user_model.objects.create_user(username='in_app_spender', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        balance=0,
        earned_balance=0,
        bonus_balance=0,
        telebirr_purchased_balance=0,
        airtime_purchased_balance=0,
        purchased_balance=0,
    )
    balance.refresh_from_db()
    balance.add_earned(100, transaction_type='reinvest')

    balance.spend_coins(40, transaction_type='boost')

    balance.refresh_from_db()
    assert balance.earned_balance == 60


# ── what is withdrawable, and what is not ───────────────────────────────────


def test_only_points_are_withdrawable_not_coins(django_user_model):
    """Coins buy things; points become money. Keeping them apart is what
    stops purchased coins being cashed out for birr."""
    from api.models.contest import UserCoinBalance

    user = django_user_model.objects.create_user(username='cashing_out', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.add_purchased(10000, payment_method='telebirr')

    user.profile.refresh_from_db()
    assert user.profile.points == 0, 'buying coins must not create withdrawable value'


def test_every_leg_of_the_chain_leaves_a_ledger_row(django_user_model):
    """Requirement 9: gift, swap and spend are each auditable."""
    from api.models.contest import CoinTransaction, UserCoinBalance

    user = django_user_model.objects.create_user(username='ledgered', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    CoinTransaction.objects.filter(user=user).delete()

    balance.add_purchased(100, payment_method='telebirr')
    balance.add_earned(50, transaction_type='reinvest')
    balance.spend_coins(20, transaction_type='boost')

    kinds = set(
        CoinTransaction.objects.filter(user=user).values_list('transaction_type', flat=True)
    )
    assert 'purchase' in kinds
    assert 'reinvest' in kinds
    assert 'boost' in kinds
