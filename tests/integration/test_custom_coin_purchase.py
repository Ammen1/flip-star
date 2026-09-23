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


# ── the same choice inside the telebirr SuperApp ────────────────────────────
#
# Custom amounts were web-only: the H5 order endpoint took a package_id and
# nothing else, so a buyer inside the SuperApp saw five fixed offers while a
# buyer on the web could type any amount. Both now price the same way, and the
# pricing is the server's either way -- the client sends money, never coins.


@pytest.fixture
def h5_buyer(django_user_model):
    """A signed-in subscriber: coin purchases are refused without access."""
    from datetime import timedelta

    from django.utils import timezone

    from api.models import SubscriptionTier
    from api.models.subscription import SubscriptionPlan

    user = django_user_model.objects.create_user(username='h5_buyer', password='x')
    SubscriptionPlan.objects.create(
        user=user,
        tier=SubscriptionTier.objects.filter(duration_type='monthly').first(),
        status='active',
        start_date=timezone.now() - timedelta(days=1),
        end_date=timezone.now() + timedelta(days=30),
    )
    UserCoinBalance.objects.get_or_create(user=user)
    return user


@pytest.fixture
def h5_order():
    """Call the real H5 initiate view, with telebirr mocked."""
    import json
    from unittest.mock import patch

    import fakeredis
    from rest_framework.test import APIRequestFactory, force_authenticate

    from api.views.wallet import telebirr_initiate_payment
    from common.security.e2e_encryption import decrypt_payload, encrypt_payload, generate_keypair
    from infrastructure.keys import key_manager, redis_store

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    server_public = key_manager.get_public_key()
    client_public, client_private = generate_keypair()

    def _order(user, body, *, merch_order_id='MO-1'):
        envelope = encrypt_payload(
            body, receiver_public_key_b64=server_public, sender_private_key_b64=client_private
        ).to_dict()
        request = APIRequestFactory().post(
            '/wallet/telebirr/initiate/',
            data=json.dumps(envelope),
            content_type='application/json',
            HTTP_X_CLIENT_PUBLIC_KEY=client_public,
        )
        force_authenticate(request, user=user)
        with patch('api.views.wallet.telebirr_service') as service:
            service.create_order_ondemand.return_value = {
                'success': True,
                'raw_request': 'signed-blob',
                'merch_order_id': merch_order_id,
                'prepay_id': 'PP-1',
            }
            response = telebirr_initiate_payment(request)
            response.render()
            called = service.create_order_ondemand.call_args
        payload = json.loads(response.content)
        if isinstance(payload, dict) and 'encrypted' in payload:
            payload = json.loads(
                decrypt_payload(
                    payload['encrypted'],
                    payload['nonce'],
                    server_public,
                    payload['checksum'],
                    client_private,
                )
            )
        return response.status_code, payload, called

    yield _order
    key_manager.reset()
    redis_store.reset_client()


def test_the_superapp_can_buy_a_typed_amount(h5_buyer, h5_order, packages, config):
    status_code, body, called = h5_order(h5_buyer, {'amount_etb': '5'})

    assert status_code == 200
    assert body['success'] is True
    assert body['raw_request'] == 'signed-blob'
    # 5 Birr at 10 coins/Birr, and the server says so -- not the client.
    assert body['coins'] == 50
    assert called.kwargs['amount'] == '5.00'


def test_a_typed_amount_records_what_to_credit(h5_buyer, h5_order, packages, config):
    """With no package there is nothing else to derive the coins from.

    _credit_telebirr_order falls back to quoted_coins; without it recorded, a
    paid purchase credits zero and is still marked successful.
    """
    h5_order(h5_buyer, {'amount_etb': '5'})

    tx = CoinTransaction.objects.get(payment_reference='MO-1')
    assert tx.package is None
    assert tx.quoted_coins == 50
    assert tx.amount_etb == Decimal('5.00')
    assert tx.coins == 0, 'coins are credited on confirmation, not at order time'


def test_a_paid_superapp_custom_order_credits_the_quoted_coins(
    h5_buyer, h5_order, packages, config
):
    from api.views.wallet import _credit_telebirr_order

    h5_order(h5_buyer, {'amount_etb': '5'})

    handled, added = _credit_telebirr_order('MO-1')

    assert handled is True
    assert added == 50
    assert UserCoinBalance.objects.get(user=h5_buyer).total_purchased == 50


def test_a_typed_amount_matching_a_package_gets_its_bonus(h5_buyer, h5_order, packages, config):
    """25 Birr is a package price, so the buyer gets the package's 275."""
    status_code, body, called = h5_order(h5_buyer, {'amount_etb': '25'})

    assert status_code == 200
    assert body['coins'] == 275
    assert called.kwargs['amount'] == '25.00'
    tx = CoinTransaction.objects.get(payment_reference='MO-1')
    assert tx.package is not None


def test_the_superapp_client_cannot_name_its_own_coin_figure(h5_buyer, h5_order, packages, config):
    status_code, body, _called = h5_order(h5_buyer, {'amount_etb': '5', 'coins': 99999})

    assert status_code == 200
    assert body['coins'] == 50
    assert CoinTransaction.objects.get(payment_reference='MO-1').quoted_coins == 50


@pytest.mark.parametrize(
    ('amount', 'code'),
    [
        ('0.99', 'below_minimum'),
        ('1000.01', 'above_maximum'),
        ('0', 'amount_not_positive'),
        ('5abc', 'amount_invalid'),
    ],
)
def test_an_unbuyable_typed_amount_is_refused(h5_buyer, h5_order, packages, config, amount, code):
    status_code, body, _called = h5_order(h5_buyer, {'amount_etb': amount})

    assert status_code == 400
    assert body['code'] == code
    # Only purchases: creating the account already wrote a welcome-bonus row.
    assert not CoinTransaction.objects.filter(
        transaction_type='purchase', payment_method='telebirr'
    ).exists(), 'an order was recorded for a refused amount'


def test_an_order_needs_a_package_or_an_amount(h5_buyer, h5_order, packages, config):
    status_code, body, _called = h5_order(h5_buyer, {})

    assert status_code == 400
    assert 'package_id or amount_etb' in body['error']


def test_the_package_path_is_unchanged(h5_buyer, h5_order, packages, config):
    package = packages[1]

    status_code, body, called = h5_order(h5_buyer, {'package_id': package.id})

    assert status_code == 200
    assert body['package']['id'] == package.id
    assert body['package']['total_coins'] == package.get_total_coins()
    assert body['coins'] == package.get_total_coins()
    assert called.kwargs['title'] == package.name
    assert called.kwargs['amount'] == f'{float(package.price_etb):.2f}'
    tx = CoinTransaction.objects.get(payment_reference='MO-1')
    assert tx.package_id == package.id
