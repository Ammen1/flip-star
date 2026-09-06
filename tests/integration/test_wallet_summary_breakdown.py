"""
The wallet summary must break `purchased` into its two kinds.

What the screen showed
----------------------
A user holding 421 coins saw:

    COINS  421
    Earned    0
    Telebirr  0
    Airtime   0

The total was right and every component was zero, which reads as a broken
balance rather than a missing breakdown. The cause was in the payload, not the
page: the response carried `total`, `earned` and `purchased`, while the wallet
screen has always read `telebirr_purchased` and `airtime_purchased`. Those
resolved to undefined and rendered as 0, and `earned` was genuinely 0 because
every coin had been bought.

Why the split is worth sending
------------------------------
The two are not interchangeable. `spend_coins(restrict_earned=True)` -- used
for gifting -- draws only on telebirr_purchased_balance, so airtime coins
cannot be gifted. A user with 421 airtime coins and a failing gift needs to be
able to see why.
"""

import fakeredis
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.contest import UserCoinBalance
from api.views.wallet import wallet_summary
from common.security.e2e_encryption import generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


@pytest.fixture
def server_keys(db):
    """wallet_summary carries @encrypted_endpoint, so the server needs keys.

    The decorator seals the RESPONSE, so even a GET with no body is refused
    without X-Client-Public-Key.
    """
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def client_keys():
    return generate_keypair()


@pytest.fixture
def holder():
    user = User.objects.create_user(username='wallet_holder', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    # Written directly rather than through add/spend so the split is exactly
    # what the assertions describe, whatever the crediting helpers do.
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        earned_balance=21,
        telebirr_purchased_balance=300,
        airtime_purchased_balance=100,
        purchased_balance=400,
        balance=421,
    )
    return user


def summary_for(user, client_keys):
    client_public_key, _ = client_keys
    request = factory.get('/wallet/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)
    force_authenticate(request, user=user)
    response = wallet_summary(request)
    assert response.status_code == 200, response.data
    return response.data


def test_every_field_the_wallet_screen_reads_is_present(holder, server_keys, client_keys):
    """
    Pinned by name.

    The screen reads balance.telebirr_purchased and balance.airtime_purchased;
    neither was sent. Listing them here means a rename on either side fails
    the build rather than silently rendering zeroes.
    """
    balance = summary_for(holder, client_keys)['balance']

    for field in ('total', 'earned', 'purchased', 'telebirr_purchased', 'airtime_purchased'):
        assert field in balance, f'{field} missing -- the wallet screen renders 0 for it'


def test_the_breakdown_reports_the_real_figures(holder, server_keys, client_keys):
    balance = summary_for(holder, client_keys)['balance']

    assert balance['total'] == 421
    assert balance['earned'] == 21
    assert balance['telebirr_purchased'] == 300
    assert balance['airtime_purchased'] == 100


def test_the_parts_account_for_the_whole(holder, server_keys, client_keys):
    """
    The arithmetic a user does in their head.

    Three components that do not add up to the total shown above them is the
    same failure as showing zeroes -- it just takes a moment longer to notice.
    """
    balance = summary_for(holder, client_keys)['balance']

    parts = balance['earned'] + balance['telebirr_purchased'] + balance['airtime_purchased']
    assert parts == balance['total']


def test_purchased_is_the_sum_of_its_two_kinds(holder, server_keys, client_keys):
    balance = summary_for(holder, client_keys)['balance']

    assert balance['purchased'] == balance['telebirr_purchased'] + balance['airtime_purchased']


def test_a_new_wallet_reports_zeroes_rather_than_omitting_fields(server_keys, client_keys):
    """
    An empty wallet must still send the keys.

    Omitting them for a zero balance would make the screen fall back to
    undefined again, which is the bug this fixes -- just for a narrower set of
    users.
    """
    user = User.objects.create_user(username='empty_wallet', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        earned_balance=0,
        telebirr_purchased_balance=0,
        airtime_purchased_balance=0,
        purchased_balance=0,
        balance=0,
    )

    result = summary_for(user, client_keys)['balance']

    assert result['telebirr_purchased'] == 0
    assert result['airtime_purchased'] == 0


def test_only_telebirr_coins_are_giftable(holder):
    """
    Why the split is shown at all.

    spend_coins(restrict_earned=True) draws solely on the telebirr balance, so
    a user holding only airtime coins cannot gift despite a healthy total. The
    breakdown is what lets them see that before the attempt fails.
    """
    balance = UserCoinBalance.objects.get(user=holder)

    balance.spend_coins(250, 'gift_sent', restrict_earned=True)

    balance.refresh_from_db()
    assert balance.telebirr_purchased_balance == 50
    assert balance.airtime_purchased_balance == 100, 'airtime coins were used for a gift'
