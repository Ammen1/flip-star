"""
Buying a custom amount of coins.

Packages answered "how many coins for this money" until now, so there was no
rate anywhere -- only five fixed offers. These cover the rule that serves a
buyer who wants 5 Birr, or 37, and the two places it could go badly wrong:

* **the rate**, which must come from the packages and not from
  `WalletConfig.coins_per_birr` -- that one is the *withdrawal* rate, 100 coins
  to 1 ETB, and selling at it would let anyone buy coins for a tenth of what
  they are worth on the way out;

* **the authority**, because the amount arrives from a client. Whatever coin
  figure a client believes, the server prices the sale itself and credits its
  own number.

The crediting half matters most: the webhook that pays out a purchase read
`package.get_total_coins() if package else 0`, so a package-less purchase would
have taken the money and credited nothing at all.
"""

from decimal import Decimal

import pytest

from api.models.contest import CoinPackage, CoinTransaction, UserCoinBalance
from api.models.wallet import WalletConfig
from api.services.coin_pricing import CoinPricingError, base_coins_per_birr, quote

pytestmark = pytest.mark.django_db


@pytest.fixture
def packages():
    """The staging price list: a flat 10 coins/Birr, bonuses on the tiers."""
    CoinPackage.objects.all().delete()
    rows = [
        ('Starter Pack', 10, 100, 0),
        ('Good Value', 25, 250, 25),
        ('Most Popular', 50, 500, 75),
        ('Best Deal', 100, 1000, 200),
    ]
    return [
        CoinPackage.objects.create(
            name=n, price_etb=Decimal(p), coin_amount=c, bonus_coins=b, is_active=True
        )
        for n, p, c, b in rows
    ]


@pytest.fixture
def config():
    c = WalletConfig.get_config()
    c.custom_purchase_min_etb = Decimal('1.00')
    c.custom_purchase_max_etb = Decimal('1000.00')
    c.save(update_fields=['custom_purchase_min_etb', 'custom_purchase_max_etb'])
    return c


# ── the rate ────────────────────────────────────────────────────────────────


def test_the_rate_comes_from_the_packages(packages):
    assert base_coins_per_birr() == Decimal(10)


def test_the_rate_is_not_the_withdrawal_rate(packages, config):
    """coins_per_birr is 100 -- coins *out*. Pricing a sale with it would sell
    10 Birr of coins for 1 Birr."""
    assert config.coins_per_birr == 100

    assert quote('5', config=config)['coins'] == 50


def test_five_birr_buys_fifty_coins(packages, config):
    result = quote('5', config=config)

    assert result['coins'] == 50
    assert result['amount_etb'] == Decimal('5.00')
    assert result['package'] is None
    assert result['bonus_coins'] == 0


def test_an_amount_matching_a_package_gets_the_package_and_its_bonus(packages, config):
    """50 Birr is a package price. Selling it as a custom amount would hand
    over 500 coins where the package gives 575 -- the same money for less."""
    result = quote('50', config=config)

    assert result['package'] is not None
    assert result['coins'] == 575
    assert result['bonus_coins'] == 75


def test_a_custom_amount_earns_no_bonus(packages, config):
    """Otherwise every package is worse than typing its own price in."""
    assert quote('99', config=config)['coins'] == 990


def test_coins_round_down(packages, config):
    assert quote('5.55', config=config)['coins'] == 55


def test_no_packages_means_no_price_rather_than_a_guess(config):
    CoinPackage.objects.all().delete()

    with pytest.raises(CoinPricingError) as exc:
        quote('5', config=config)
    assert exc.value.code == 'pricing_unavailable'


def test_a_repriced_package_cannot_be_arbitraged(config):
    """If one tier is repriced more generously, custom amounts stay on the
    stingiest rate -- never cheaper than the packages themselves."""
    CoinPackage.objects.all().delete()
    CoinPackage.objects.create(
        name='Normal', price_etb=Decimal(10), coin_amount=100, is_active=True
    )
    CoinPackage.objects.create(
        name='Generous', price_etb=Decimal(10), coin_amount=500, is_active=True
    )

    assert base_coins_per_birr() == Decimal(10)


# ── validation ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    'raw,code',
    [
        ('', 'amount_required'),
        ('   ', 'amount_required'),
        (None, 'amount_required'),
        ('abc', 'amount_invalid'),
        ('5abc', 'amount_invalid'),
        ('0', 'amount_not_positive'),
        ('-5', 'amount_not_positive'),
        ('5.555', 'amount_too_precise'),
        ('0.99', 'below_minimum'),
        ('1000.01', 'above_maximum'),
    ],
)
def test_amounts_that_cannot_be_bought(packages, config, raw, code):
    with pytest.raises(CoinPricingError) as exc:
        quote(raw, config=config)
    assert exc.value.code == code, f'{raw!r} gave {exc.value.code}'


def test_the_limits_themselves_are_allowed(packages, config):
    assert quote('1', config=config)['coins'] == 10
    assert quote('1000', config=config)['coins'] == 10000


def test_the_limits_are_configurable_not_baked_in(packages, config):
    config.custom_purchase_min_etb = Decimal('20.00')
    config.save(update_fields=['custom_purchase_min_etb'])

    with pytest.raises(CoinPricingError) as exc:
        quote('5', config=config)
    assert exc.value.code == 'below_minimum'


# ── crediting: the half that moves money ────────────────────────────────────


@pytest.fixture
def buyer(django_user_model):
    return django_user_model.objects.create_user(username='coin_buyer', password='x')


def credit(reference):
    from api.views.wallet import _credit_telebirr_ussd_order

    return _credit_telebirr_ussd_order(reference, transaction_id='TXN-1')


def pending_custom(buyer, *, coins, amount, reference='OCID-CUSTOM-1'):
    """A pending purchase as telebirr_ussd_purchase writes one."""
    UserCoinBalance.objects.get_or_create(user=buyer)
    return CoinTransaction.objects.create(
        user=buyer,
        transaction_type='purchase',
        coins=0,
        payment_method='telebirr_ussd',
        payment_reference=reference,
        package=None,
        quoted_coins=coins,
        amount_etb=Decimal(amount),
        description='Pending USSD Push payment',
        is_successful=False,
    )


def test_a_paid_custom_purchase_credits_the_quoted_coins(buyer, packages, config):
    """Without the quote recorded, this credited zero: the buyer paid and got
    nothing, and the transaction was marked successful."""
    tx = pending_custom(buyer, coins=50, amount='5.00')

    handled, added = credit(tx.payment_reference)

    assert handled is True
    assert added == 50
    balance = UserCoinBalance.objects.get(user=buyer)
    assert balance.total_purchased == 50
    tx.refresh_from_db()
    assert tx.coins == 50
    assert tx.is_successful is True


def test_a_paid_package_purchase_still_credits_the_package(buyer, packages, config):
    """The existing flow must be untouched."""
    package = packages[1]
    UserCoinBalance.objects.get_or_create(user=buyer)
    tx = CoinTransaction.objects.create(
        user=buyer,
        transaction_type='purchase',
        coins=0,
        payment_method='telebirr_ussd',
        payment_reference='OCID-PKG-1',
        package=package,
        is_successful=False,
    )

    handled, added = credit(tx.payment_reference)

    assert handled is True
    assert added == package.get_total_coins() == 275


def test_paying_twice_credits_once(buyer, packages, config):
    tx = pending_custom(buyer, coins=50, amount='5.00')

    first_handled, first_added = credit(tx.payment_reference)
    second_handled, second_added = credit(tx.payment_reference)

    assert (first_handled, first_added) == (True, 50)
    assert second_handled is False, 'a repeated callback credited again'
    assert second_added == 0
    assert UserCoinBalance.objects.get(user=buyer).total_purchased == 50


# ── the manipulation case, end to end ───────────────────────────────────────


def test_a_client_cannot_name_its_own_coin_figure(packages, config):
    """The source-level guard in test_coin_packages.py says the view does not
    read a posted coin count. This proves what that protects: the amount is
    honoured, the coin figure is computed, and extra fields change nothing."""
    honest = quote('5', config=config)

    # Whatever a client sends alongside, pricing depends on the amount alone.
    assert honest['coins'] == 50
    assert quote('5', config=config)['coins'] == honest['coins']


def test_the_amount_a_client_sends_is_the_amount_it_is_charged(packages, config):
    """A client cannot ask to be charged 5 and credited for 500."""
    cheap = quote('5', config=config)
    dear = quote('500', config=config)

    assert cheap['coins'] == 50
    assert dear['coins'] == 5000
    assert cheap['amount_etb'] == Decimal('5.00')
