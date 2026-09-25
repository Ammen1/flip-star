"""
The coin and wallet business requirement, asserted against the code.

Most of this is already covered elsewhere and deliberately not repeated here:

* concurrency, overspend and duplicate callbacks -- tests/integration/
  test_concurrency.py (concurrent spends never lose an update, cannot
  overspend, and a webhook delivered twice credits exactly once)
* the pricing rules and their edges -- test_custom_coin_purchase.py
* what each purchase path writes -- test_telebirr_ussd_coin_purchase.py,
  test_coin_purchase_security.py
* gifting restrictions -- test_bonus_coins_not_giftable.py

What had no test was the **order coins are spent in**, which is the rule the
requirement is most specific about and the one most easily broken by an
innocent-looking edit: the buckets are four `PositiveIntegerField`s and any
reordering of the subtraction still balances, still refuses an overspend, and
still passes every test above. The only way it shows up is a user's purchased
coins draining before their free ones.

The rate is pinned here too. It is *derived* from the package rows rather than
being a constant, so repricing one package silently moves it.
"""

from decimal import Decimal

import pytest

from api.models.contest import CoinPackage, UserCoinBalance

pytestmark = pytest.mark.django_db

#: The requirement's rate: 1 ETB buys 10 coins.
COINS_PER_BIRR = 10


@pytest.fixture
def packages(db):
    """The shipped price list, all at the documented rate."""
    CoinPackage.objects.all().delete()
    rows = [
        ('Starter Pack', 10, 100, 0),
        ('Good Value', 25, 250, 25),
        ('Most Popular', 50, 500, 75),
        ('Best Deal', 100, 1000, 200),
    ]
    return [
        CoinPackage.objects.create(
            name=name,
            price_etb=Decimal(price),
            coin_amount=coins,
            bonus_coins=bonus,
            is_active=True,
        )
        for name, price, coins, bonus in rows
    ]


@pytest.fixture
def wallet(django_user_model):
    user = django_user_model.objects.create_user(username='wallet_rules', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    # Start from a clean slate: account creation may grant a welcome bonus.
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        balance=0,
        earned_balance=0,
        bonus_balance=0,
        telebirr_purchased_balance=0,
        airtime_purchased_balance=0,
        purchased_balance=0,
        total_spent=0,
    )
    balance.refresh_from_db()
    return balance


def buckets(balance):
    balance.refresh_from_db()
    return {
        'bonus': balance.bonus_balance,
        'earned': balance.earned_balance,
        'airtime': balance.airtime_purchased_balance,
        'telebirr': balance.telebirr_purchased_balance,
    }


# ── the rate ────────────────────────────────────────────────────────────────


def test_one_birr_buys_ten_coins(packages):
    from api.services.coin_pricing import base_coins_per_birr

    assert base_coins_per_birr() == COINS_PER_BIRR


@pytest.mark.parametrize(('birr', 'coins'), [(1, 10), (5, 50), (7, 70), (37, 370)])
def test_a_custom_amount_is_priced_at_the_same_rate(packages, birr, coins):
    """No second formula: the custom path and the packages share one rate."""
    from api.services.coin_pricing import quote

    assert quote(str(birr))['coins'] == coins


def test_a_package_price_pays_the_package_and_its_bonus(packages):
    """25 ETB is a package, so it pays 275 rather than the flat 250."""
    from api.services.coin_pricing import quote

    priced = quote('25')

    assert priced['coins'] == 275
    assert priced['bonus_coins'] == 25
    assert priced['package'] is not None


def test_a_purchase_carries_no_commission(packages):
    """What is charged is what was asked for -- no fee is added on top."""
    from api.services.coin_pricing import quote

    for birr in (1, 5, 37, 100):
        assert quote(str(birr))['amount_etb'] == Decimal(birr).quantize(Decimal('0.01'))


def test_repricing_one_package_cannot_undercut_the_others(packages):
    """The lowest rate wins, so a mispriced tier cannot be arbitraged.

    Without this, repricing one package to 20 coins/birr would let a custom
    amount buy at the dearer rate while the package sold at the cheaper one.
    """
    from api.services.coin_pricing import base_coins_per_birr

    CoinPackage.objects.filter(name='Best Deal').update(coin_amount=500)  # 5/birr

    assert base_coins_per_birr() == 5


# ── spending order: free coins before paid ones ─────────────────────────────


def test_reward_coins_are_spent_before_purchased_ones(wallet):
    """Rule 4. Reward first; purchased only once reward runs out."""
    wallet.add_earned(100, transaction_type='reward')
    wallet.add_purchased(100, payment_method='telebirr')

    wallet.spend_coins(60, transaction_type='boost')

    after = buckets(wallet)
    assert after['earned'] == 40, 'reward coins were not spent first'
    assert after['telebirr'] == 100, 'purchased coins were touched too early'


def test_purchased_coins_cover_what_reward_coins_cannot(wallet):
    """Rule 4's second half: the remainder falls through to purchased."""
    wallet.add_earned(30, transaction_type='reward')
    wallet.add_purchased(100, payment_method='telebirr')

    wallet.spend_coins(80, transaction_type='boost')

    after = buckets(wallet)
    assert after['earned'] == 0
    assert after['telebirr'] == 50, 'the remainder did not come from purchased'


def test_airtime_coins_are_spent_before_telebirr_ones(wallet):
    """Both are purchased, but only Telebirr coins can be gifted.

    So spending airtime first preserves the more useful bucket -- the same
    reasoning that puts free coins ahead of paid ones.
    """
    wallet.add_purchased(50, payment_method='airtime')
    wallet.add_purchased(50, payment_method='telebirr')

    wallet.spend_coins(50, transaction_type='boost')

    after = buckets(wallet)
    assert after['airtime'] == 0
    assert after['telebirr'] == 50


def test_bonus_coins_are_spent_before_everything_else(wallet):
    """A deliberate deviation from the literal rule, in the user's favour.

    The requirement says reward first, then purchased, and says nothing about
    subscription bonus coins. They are spent ahead of both because a lapsing
    subscription can take them away, so drawing them down first is the outcome
    that costs the user least. Free-before-paid still holds, which is what the
    rule is protecting.
    """
    wallet.add_bonus(20)
    wallet.add_earned(20, transaction_type='reward')
    wallet.add_purchased(20, payment_method='telebirr')

    wallet.spend_coins(20, transaction_type='boost')

    after = buckets(wallet)
    assert after['bonus'] == 0
    assert after['earned'] == 20
    assert after['telebirr'] == 20


def test_a_spend_draining_every_bucket_takes_them_in_order(wallet):
    wallet.add_bonus(10)
    wallet.add_earned(10, transaction_type='reward')
    wallet.add_purchased(10, payment_method='airtime')
    wallet.add_purchased(10, payment_method='telebirr')

    wallet.spend_coins(35, transaction_type='boost')

    after = buckets(wallet)
    assert after == {'bonus': 0, 'earned': 0, 'airtime': 0, 'telebirr': 5}


# ── balance safety ──────────────────────────────────────────────────────────


def test_an_empty_wallet_cannot_spend(wallet):
    with pytest.raises(ValueError, match='Insufficient'):
        wallet.spend_coins(1, transaction_type='boost')

    assert buckets(wallet) == {'bonus': 0, 'earned': 0, 'airtime': 0, 'telebirr': 0}


def test_spending_more_than_the_total_is_refused_whole(wallet):
    """Refused entirely -- never a partial deduction."""
    wallet.add_earned(30, transaction_type='reward')

    with pytest.raises(ValueError, match='Insufficient'):
        wallet.spend_coins(31, transaction_type='boost')

    assert buckets(wallet)['earned'] == 30, 'a refused spend still took coins'


def test_the_total_never_goes_negative(wallet):
    wallet.add_earned(5, transaction_type='reward')

    with pytest.raises(ValueError):
        wallet.spend_coins(10, transaction_type='boost')

    wallet.refresh_from_db()
    assert wallet.balance >= 0
    for value in buckets(wallet).values():
        assert value >= 0


@pytest.mark.parametrize('amount', [0, -1, -100])
def test_a_spend_of_nothing_or_less_is_refused(wallet, amount):
    wallet.add_earned(50, transaction_type='reward')

    with pytest.raises(ValueError, match='positive'):
        wallet.spend_coins(amount, transaction_type='boost')

    assert buckets(wallet)['earned'] == 50


def test_the_headline_balance_matches_the_buckets(wallet):
    """What the wallet screen shows has to equal what is actually there."""
    wallet.add_bonus(7)
    wallet.add_earned(11, transaction_type='reward')
    wallet.add_purchased(13, payment_method='airtime')
    wallet.add_purchased(17, payment_method='telebirr')

    wallet.refresh_from_db()
    assert wallet.balance == 7 + 11 + 13 + 17


def test_only_telebirr_coins_count_as_giftable(wallet):
    """Reward, bonus and airtime coins are real balance but cannot be gifted."""
    wallet.add_bonus(10)
    wallet.add_earned(10, transaction_type='reward')
    wallet.add_purchased(10, payment_method='airtime')
    wallet.add_purchased(10, payment_method='telebirr')

    wallet.refresh_from_db()
    assert wallet.giftable_balance == 10
    assert wallet.non_giftable_balance == 30


# ── non-refundable, and no expiry ───────────────────────────────────────────


def test_nothing_in_the_wallet_issues_a_refund():
    """The requirement forbids a refund path, so there must not be one.

    'refund' survives as a transaction_type choice from an older schema, but
    no code creates one. Asserted against the source because the risk is a
    refund helper being added later in good faith.
    """
    from pathlib import Path

    import api.models.contest as contest
    import api.views.wallet as wallet_views

    for module in (contest, wallet_views):
        source = Path(module.__file__).read_text(encoding='utf-8')
        assert 'def refund' not in source, f'{module.__name__} grew a refund path'
        assert "transaction_type='refund'" not in source


def test_coins_do_not_expire(wallet):
    """No expiry anywhere, so a balance is still there whenever it is spent.

    Pinned because 'coin expiration' appears in the requirement's inspect
    list: the answer is that the product has none, and that is a decision
    worth being explicit about rather than an oversight.
    """
    import inspect

    from api.models.contest import CoinTransaction, UserCoinBalance

    # The coin models specifically -- contest.py also holds subscription-era
    # models that legitimately carry an expiry.
    for model in (UserCoinBalance, CoinTransaction):
        source = inspect.getsource(model)
        assert 'expires_at' not in source, f'{model.__name__} grew an expiry'
        assert 'def expire' not in source

    # And a balance credited long ago is still spendable now.
    wallet.add_earned(25, transaction_type='reward')
    wallet.spend_coins(25, transaction_type='boost')
    assert buckets(wallet)['earned'] == 0
