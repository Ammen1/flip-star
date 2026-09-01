"""
Coins are credited only by a confirmed payment, once.

The popup lets a user buy without leaving what they were doing, which makes
the purchase path easier to reach -- so the guarantees behind it are pinned
here: no crediting without a payment, the amount comes from the package and
never from the request, and a webhook that arrives twice credits once.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from api.models.contest import CoinPackage, CoinTransaction, UserCoinBalance
from api.services.coin_purchase import insufficient_coins_payload, auth_required_payload
from api.views.wallet import _credit_telebirr_ussd_order

pytestmark = pytest.mark.integration

PURCHASE_URL = '/api/v1/coins/purchase/'


def post_purchase(user, package_id, keys):
    """Call the endpoint exactly the way a real client does.

    It sits behind the E2E transport, so both the header and an *encrypted
    body* are required. Sending plaintext is rejected by the parser before the
    view runs -- which would make this look like a pass for the wrong reason,
    since a view that never touches request.data never triggers the parser.
    """
    from common.security.e2e_encryption import encrypt_payload

    server_public, client_public, client_private = keys
    sealed = encrypt_payload({'package_id': package_id}, server_public, client_private)

    api = APIClient()
    api.force_authenticate(user=user)
    return api.post(
        PURCHASE_URL,
        {
            'encrypted': sealed['encrypted'],
            'nonce': sealed['nonce'],
            'checksum': sealed['checksum'],
        },
        format='json',
        HTTP_X_CLIENT_PUBLIC_KEY=client_public,
    )


@pytest.fixture
def user(db):
    u = User.objects.create_user(username='coin_user', password='x')
    yield u
    u.delete()


@pytest.fixture
def package(db):
    p = CoinPackage.objects.create(
        name='Starter', price_etb=Decimal('10.00'), coin_amount=100,
        bonus_coins=20, is_active=True,
    )
    yield p
    p.delete()


def coins(user):
    """Current coin balance. New accounts start with a signup bonus, so every
    assertion below compares a delta rather than an absolute."""
    bal, _ = UserCoinBalance.objects.get_or_create(user=user)
    bal.refresh_from_db()
    return bal.balance


# ─── no crediting without a payment ───────────────────────────────────────────

def test_the_old_instant_credit_endpoint_no_longer_grants_coins(
    user, package, encrypted_client_keys
):
    """It used to add package coins on request, so any signed-in user could
    mint themselves an unlimited balance."""
    before = coins(user)
    response = post_purchase(user, package.id, encrypted_client_keys)

    assert response.status_code == 402, response.content
    assert coins(user) == before


def test_repeating_that_call_still_grants_nothing(user, package, encrypted_client_keys):
    before = coins(user)
    for _ in range(5):
        post_purchase(user, package.id, encrypted_client_keys)
    assert coins(user) == before


# ─── the amount is the server's, never the client's ───────────────────────────

def test_credited_amount_comes_from_the_package(user, package):
    before = coins(user)
    CoinTransaction.objects.create(
        user=user, transaction_type='purchase', coins=0,
        payment_method='telebirr_ussd', payment_reference='ORDER-1',
        package=package, is_successful=False,
    )

    handled, added = _credit_telebirr_ussd_order('ORDER-1', transaction_id='TX-1')

    assert handled is True
    # 100 + 20 bonus, from the package -- not from anything a client sent.
    assert added == package.get_total_coins() == 120
    assert coins(user) == before + 120


def test_a_client_supplied_coin_amount_is_ignored(user, package):
    """The pending row is keyed to a package; there is no field a caller could
    use to ask for more."""
    before = coins(user)
    CoinTransaction.objects.create(
        user=user, transaction_type='purchase',
        coins=999999,  # a hostile value sitting on the pending row
        payment_method='telebirr_ussd', payment_reference='ORDER-2',
        package=package, is_successful=False,
    )

    _handled, added = _credit_telebirr_ussd_order('ORDER-2', transaction_id='TX-2')

    assert added == 120
    assert coins(user) == before + 120


# ─── no double crediting ──────────────────────────────────────────────────────

def test_a_repeated_webhook_credits_only_once(user, package):
    before = coins(user)
    CoinTransaction.objects.create(
        user=user, transaction_type='purchase', coins=0,
        payment_method='telebirr_ussd', payment_reference='ORDER-3',
        package=package, is_successful=False,
    )

    first_handled, first_added = _credit_telebirr_ussd_order('ORDER-3', transaction_id='TX-3')
    second_handled, second_added = _credit_telebirr_ussd_order('ORDER-3', transaction_id='TX-3')

    assert (first_handled, first_added) == (True, 120)
    # Second delivery is a no-op, not another 120 coins.
    assert (second_handled, second_added) == (False, 0)
    assert coins(user) == before + 120


def test_an_unknown_order_credits_nothing(user):
    before = coins(user)
    handled, added = _credit_telebirr_ussd_order('NO-SUCH-ORDER')
    assert (handled, added) == (False, 0)
    assert coins(user) == before


# ─── the popup's error contract ───────────────────────────────────────────────

def test_insufficient_and_auth_failures_are_distinguishable():
    """The popup shows packages for one and a sign-in button for the other, so
    they must never be told apart by prose."""
    short = insufficient_coins_payload(50, 12)
    auth = auth_required_payload()

    assert short['code'] == 'INSUFFICIENT_COINS'
    assert auth['code'] == 'AUTH_REQUIRED'
    assert short['code'] != auth['code']


def test_the_shortfall_is_computed_server_side():
    payload = insufficient_coins_payload(50, 12)
    assert payload['required_coins'] == 50
    assert payload['current_coins'] == 12
    assert payload['shortfall'] == 38


def test_a_balance_above_the_requirement_reports_no_negative_shortfall():
    assert insufficient_coins_payload(10, 999)['shortfall'] == 0
