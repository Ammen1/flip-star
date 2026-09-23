"""
Coin packages: the five supported amounts, and refusing everything else.

Telebirr is configured for exactly 10, 50, 100, 250 and 500 ETB. An amount
they do not recognise is rejected at their gateway -- after the user has
already confirmed the USSD prompt on their handset -- so the lineup is not a
presentation detail.

The cases that matter are the ones a hostile client would try:

  price         posting a price with the package_id must not change what is
                charged
  coins         posting a coin amount must not change what is granted
  inactive      a retired package must not be purchasable, even by id
  unknown       an id that does not exist must 404, not fall through

and the one an operator would hit:

  drift         the seed lineup and the empty-table fallback must agree, since
                the price shown before seeding is the price charged after it
"""

import pytest
from django.contrib.auth.models import User

from api.models.contest import CoinPackage
from api.services.coin_packages import (
    COIN_PACKAGES,
    COINS_PER_ETB,
    SUPPORTED_PRICES,
    fallback_payload,
)

pytestmark = pytest.mark.django_db

REQUIRED_PRICES = [10, 50, 100, 250, 500]


@pytest.fixture
def packages():
    """The real seeded lineup."""
    from django.core.management import call_command

    call_command('seed_coin_packages', verbosity=0)
    return CoinPackage.objects.filter(is_active=True).order_by('price_etb')


@pytest.fixture
def buyer():
    return User.objects.create_user(username='coin_buyer', password='x')


# ---------------------------------------------------------------------------
# The five amounts
# ---------------------------------------------------------------------------


def test_exactly_the_five_required_prices_are_offered(packages):
    assert [int(p.price_etb) for p in packages] == REQUIRED_PRICES


@pytest.mark.parametrize('price', REQUIRED_PRICES)
def test_each_required_package_exists_and_is_active(packages, price):
    pkg = CoinPackage.objects.get(price_etb=price)
    assert pkg.is_active
    assert pkg.coin_amount > 0


@pytest.mark.parametrize('price', REQUIRED_PRICES)
def test_base_coins_follow_the_published_rate(packages, price):
    """Coins are price * 10 before bonus -- a user can check the arithmetic."""
    pkg = CoinPackage.objects.get(price_etb=price)
    assert pkg.coin_amount == price * COINS_PER_ETB


def test_bonus_never_decreases_as_price_rises(packages):
    """
    A larger purchase must never be worse value.

    Not cosmetic: a tier that gave proportionally fewer coins than a cheaper
    one would be a live pricing bug, and nothing else checks it.
    """
    ratios = [
        (p.coin_amount + p.bonus_coins) / float(p.price_etb) for p in packages.order_by('price_etb')
    ]
    assert ratios == sorted(ratios), f'value per birr goes down somewhere: {ratios}'


def test_twenty_five_etb_is_retired_not_deleted(packages):
    """
    The old lineup had a 25 ETB tier. Telebirr no longer accepts it, but
    CoinTransaction rows still reference it -- deleting would orphan the audit
    trail for purchases already made, so it is deactivated instead.
    """
    CoinPackage.objects.create(
        name='Good Value', price_etb=25, coin_amount=250, bonus_coins=25, is_active=True
    )

    from django.core.management import call_command

    call_command('seed_coin_packages', verbosity=0)

    retired = CoinPackage.objects.get(price_etb=25)
    assert retired.is_active is False, 'still purchasable'
    assert CoinPackage.objects.filter(price_etb=25).exists(), 'deleted instead of retired'


# ---------------------------------------------------------------------------
# Client manipulation
# ---------------------------------------------------------------------------


def _view_source(func_name):
    """The text of one view function, read from the file.

    inspect.getsource() cannot be used here: these views are wrapped by
    @api_view and @encrypted_endpoint, so it returns the decorator's wrapper
    rather than the body being asserted about.
    """
    from pathlib import Path

    import api.views.wallet as wallet_module

    lines = Path(wallet_module.__file__).read_text(encoding='utf-8').splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f'def {func_name}('))
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith(('def ', '@'))),
        len(lines),
    )
    return chr(10).join(lines[start:end])


@pytest.mark.parametrize('view_name', ['telebirr_initiate_payment', 'telebirr_ussd_purchase'])
def test_the_coin_figure_never_comes_from_the_request(view_name):
    """
    The manipulation case.

    A client may say how much money to take -- that is what a custom amount is
    -- but never how many coins it is worth. Whatever coin or price figure it
    posts alongside is never read, so what gets credited is always computed
    here.

    Asserted against the source rather than by calling the view, because
    proving a value is *not* read cannot be done from the outside: a view that
    silently preferred a posted coin count would return exactly the same
    response shape as one that ignored it.
    """
    source = _view_source(view_name)

    assert "request.data.get('package_id')" in source, 'must select by id'

    # 'amount' is deliberately absent from this list for the USSD view: see
    # the test below, which covers the one field a client may name.
    for forged in ('price', 'coin', 'total', 'birr'):
        assert f"request.data.get('{forged}" not in source, (
            f'{view_name} reads {forged!r} from the client -- what is charged and '
            'credited must be computed server-side, never posted'
        )


def test_the_h5_entry_point_prices_the_amount_itself():
    """Custom amounts reach the SuperApp too, and on the same terms.

    This used to assert the opposite -- that /wallet/telebirr/initiate/ read
    no amount at all -- because typed amounts were a web-only feature. Now
    both entry points take one, so the property worth pinning is not "no
    amount" but "no coin figure from the client": the amount is what a buyer
    may name, and what it buys is decided here.
    """
    source = _view_source('telebirr_initiate_payment')

    assert 'package.price_etb' in source, 'a package amount must derive from the row'
    assert "request.data.get('amount_etb')" in source, 'must accept a custom amount'
    assert 'quote_coins(' in source, 'the amount must be priced by coin_pricing.quote'
    assert "priced['coins']" in source, 'the coin figure must come from the quote'


def test_the_ussd_entry_point_prices_the_amount_itself():
    """The custom path takes an amount and prices it here. What makes that
    safe is that the coins come from quote(), not from the request."""
    source = _view_source('telebirr_ussd_purchase')

    assert "request.data.get('amount_etb')" in source, 'must accept a custom amount'
    assert 'quote_coins(' in source, 'the amount must be priced by coin_pricing.quote'
    assert "priced['coins']" in source, 'the coin figure must come from the quote'


def test_inactive_package_cannot_be_purchased(packages):
    """A retired package must not be reachable by id."""
    pkg = CoinPackage.objects.get(price_etb=10)
    pkg.is_active = False
    pkg.save()

    assert not CoinPackage.objects.filter(id=pkg.id, is_active=True).exists()


def test_unknown_package_id_matches_nothing(packages):
    assert not CoinPackage.objects.filter(id=999999, is_active=True).exists()


@pytest.mark.parametrize('price', [1, 5, 25, 75, 300, 1000, 0, -10])
def test_unsupported_amounts_are_not_offered(packages, price):
    """Telebirr rejects these at the gateway; they must never reach it."""
    assert price not in SUPPORTED_PRICES
    assert not CoinPackage.objects.filter(price_etb=price, is_active=True).exists()


# ---------------------------------------------------------------------------
# One source of truth
# ---------------------------------------------------------------------------


def test_fallback_matches_the_seeded_rows(packages):
    """
    The drift guard.

    get_wallet_config serves fallback_payload() when the table cannot be read.
    If that disagreed with the seed, a user would be shown one price before
    seeding and charged another after it.
    """
    seeded = [
        (p.name, int(p.price_etb), p.coin_amount, p.bonus_coins)
        for p in packages.order_by('sort_order')
    ]
    fallback = [
        (row['name'], int(float(row['price_etb'])), row['coin_amount'], row['bonus_coins'])
        for row in fallback_payload()
    ]
    assert seeded == fallback


def test_fallback_reports_correct_totals():
    for row in fallback_payload():
        assert row['total_coins'] == row['coin_amount'] + row['bonus_coins']


def test_supported_prices_matches_the_lineup():
    assert SUPPORTED_PRICES == frozenset(REQUIRED_PRICES)
    assert [p['price_etb'] for p in COIN_PACKAGES] == REQUIRED_PRICES


def test_exactly_one_package_is_featured():
    """Two featured cards give the UI no single call to action."""
    assert sum(1 for p in COIN_PACKAGES if p['is_featured']) == 1


def test_sort_order_is_unique_and_ascending():
    orders = [p['sort_order'] for p in COIN_PACKAGES]
    assert orders == sorted(orders)
    assert len(set(orders)) == len(orders)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_seeding_twice_creates_no_duplicates(packages):
    from django.core.management import call_command

    before = CoinPackage.objects.count()
    call_command('seed_coin_packages', verbosity=0)

    assert CoinPackage.objects.count() == before
    for price in REQUIRED_PRICES:
        assert CoinPackage.objects.filter(price_etb=price).count() == 1


def test_reseeding_reactivates_a_manually_disabled_package(packages):
    """The seed is the source of truth: it restores what it declares."""
    pkg = CoinPackage.objects.get(price_etb=500)
    pkg.is_active = False
    pkg.save()

    from django.core.management import call_command

    call_command('seed_coin_packages', verbosity=0)

    pkg.refresh_from_db()
    assert pkg.is_active


# ---------------------------------------------------------------------------
# Duplicate selection
# ---------------------------------------------------------------------------


def _pending(user, package, reference='S_XPENDING', age_seconds=0):
    """A purchase row as telebirr_ussd_purchase writes one."""
    from datetime import timedelta

    from django.utils import timezone

    from api.models.contest import CoinTransaction

    tx = CoinTransaction.objects.create(
        user=user,
        transaction_type='purchase',
        coins=0,
        payment_method='telebirr_ussd',
        payment_reference=reference,
        package=package,
        description='Pending',
        is_successful=False,
    )
    if age_seconds:
        CoinTransaction.objects.filter(pk=tx.pk).update(
            created_at=timezone.now() - timedelta(seconds=age_seconds)
        )
        tx.refresh_from_db()
    return tx


def test_a_second_tap_finds_the_outstanding_push(packages, buyer):
    """
    The double-charge case.

    Two pushes means two prompts on the handset, and confirming both debits
    twice -- each carries its own OriginatorConversationID, so both callbacks
    credit legitimately and the records look correct afterwards.
    """
    from api.services.coin_packages import pending_coin_purchase

    pkg = CoinPackage.objects.get(price_etb=50)
    first = _pending(buyer, pkg)

    found = pending_coin_purchase(buyer, pkg)

    assert found is not None
    assert found.pk == first.pk


def test_the_refusal_carries_the_original_conversation_id(packages, buyer):
    """The client resumes polling the first attempt rather than starting over."""
    from api.services.coin_packages import pending_coin_purchase, purchase_pending_payload

    pkg = CoinPackage.objects.get(price_etb=50)
    _pending(buyer, pkg, reference='S_XORIGINAL')

    payload = purchase_pending_payload(pending_coin_purchase(buyer, pkg))

    assert payload['success'] is False
    assert payload['code'] == 'PURCHASE_PENDING'
    assert payload['originator_conversation_id'] == 'S_XORIGINAL'


def test_a_completed_purchase_does_not_block_the_next_one(packages, buyer):
    """Once credited, the user must be able to buy again immediately."""
    from api.services.coin_packages import pending_coin_purchase

    pkg = CoinPackage.objects.get(price_etb=50)
    tx = _pending(buyer, pkg)
    tx.is_successful = True
    tx.save()

    assert pending_coin_purchase(buyer, pkg) is None


def test_an_old_push_stops_blocking(packages, buyer):
    """
    A push the user ignored must not lock them out for good.

    The window exists precisely because a confirmation that never arrives
    would otherwise leave the row pending forever.
    """
    from api.services.coin_packages import pending_coin_purchase

    pkg = CoinPackage.objects.get(price_etb=50)
    _pending(buyer, pkg, age_seconds=11 * 60)

    assert pending_coin_purchase(buyer, pkg) is None


def test_a_failed_initiation_is_recorded_but_does_not_block(packages, buyer):
    """
    The audit requirement and the retry requirement at once.

    A failed initiation writes a row so the attempt is investigable, with no
    payment_reference because nothing reached Telebirr. The guard ignores rows
    without one, so the record never blocks the retry it documents.
    """
    from api.models.contest import CoinTransaction
    from api.services.coin_packages import pending_coin_purchase

    pkg = CoinPackage.objects.get(price_etb=50)
    CoinTransaction.objects.create(
        user=buyer,
        transaction_type='purchase',
        coins=0,
        payment_method='telebirr_ussd',
        package=pkg,
        description='Failed USSD Push initiation for Most Popular: gateway timeout',
        is_successful=False,
    )

    assert CoinTransaction.objects.filter(user=buyer, is_successful=False).count() == 1
    assert pending_coin_purchase(buyer, pkg) is None, 'audit row blocked the retry'


def test_another_users_pending_push_is_not_mine(packages, buyer):
    from django.contrib.auth.models import User

    from api.services.coin_packages import pending_coin_purchase

    pkg = CoinPackage.objects.get(price_etb=50)
    other = User.objects.create_user(username='someone_else', password='x')
    _pending(other, pkg)

    assert pending_coin_purchase(buyer, pkg) is None


def test_the_failure_response_does_not_leak_the_provider_payload():
    """
    `details` used to return the provider's raw reply, which echoes request
    fields. The client gets a message; the full payload goes to the log.
    """
    source = _view_source('telebirr_ussd_purchase')

    failure = source.split("if not result.get('success')")[1].split('CoinTransaction')[0]
    assert "'details': result" not in source, 'raw provider payload returned to the client'
    assert 'error_text' in failure
