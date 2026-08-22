"""
Regression test for api/views/boost.py::create_boost_campaign's coin
deduction -- it used to only decrement UserProfile.coins directly, bypassing
UserCoinBalance/CoinTransaction (the actual wallet ledger:
api/views/wallet.py::wallet_summary reads UserCoinBalance.balance, not
UserProfile.coins). That meant a boost purchase never appeared in
wallet/transactions/ and silently desynced the two balances -- ported from
master's UserCoinBalance.spend_coins()-based version, but routed through the
locked, ledger-writing implementation already established elsewhere in this
codebase (UserCoinBalance.spend_coins) rather than master's own unlocked
coin_balance.balance read.

create_boost_campaign is gated by @encrypted_endpoint (a real Tier-1
sensitive-endpoint requirement -- see tests/unit/test_encrypted_endpoints_wiring.py),
so it's exercised through a real encrypted round trip rather than bypassed,
following the same pattern as tests/integration/test_b2c_payout.py.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

import json

import fakeredis
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.boost import BoostConfig
from api.models.contest import CoinTransaction, UserCoinBalance
from api.models.core import Reel
from api.views.boost import create_boost_campaign
from common.security.e2e_encryption import decrypt_payload, encrypt_payload, generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.integration

factory = APIRequestFactory()


@pytest.fixture
def _server_keys(db):
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


def _encrypted_envelope(plaintext_dict, *, sender_private_key, receiver_public_key):
    sealed = encrypt_payload(
        plaintext_dict, receiver_public_key_b64=receiver_public_key,
        sender_private_key_b64=sender_private_key,
    )
    return sealed.to_dict()


def _decrypt_response(response, *, server_public_key, client_private_key):
    response.render()
    envelope_out = json.loads(response.content)
    plaintext = decrypt_payload(
        envelope_out['encrypted'], envelope_out['nonce'], server_public_key,
        envelope_out['checksum'], client_private_key,
    )
    return json.loads(plaintext)


@pytest.fixture
def user_with_coins(db):
    u = User.objects.create_user(username='boost_ledger_user', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=u)
    balance.add_earned(10000, transaction_type='test_seed', description='seed for boost ledger test')
    u.profile.coins = balance.balance
    u.profile.save(update_fields=['coins'])
    yield u
    u.delete()


@pytest.fixture
def own_reel(db, user_with_coins):
    reel = Reel.objects.create(user=user_with_coins, caption='boost me')
    yield reel
    reel.delete()


@pytest.fixture(autouse=True)
def _boost_config(db):
    config = BoostConfig.objects.first() or BoostConfig.objects.create()
    yield config


def _create_campaign(user, reel, *, server_public_key, client_public_key, client_private_key, duration_hours=1):
    envelope = _encrypted_envelope(
        {'reel_id': reel.id, 'duration_hours': duration_hours},
        sender_private_key=client_private_key, receiver_public_key=server_public_key,
    )
    request = factory.post(
        '/boost/campaigns/create/', data=json.dumps(envelope), content_type='application/json',
        HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
    )
    force_authenticate(request, user=user)
    response = create_boost_campaign(request)
    return response, _decrypt_response(response, server_public_key=server_public_key, client_private_key=client_private_key)


def test_create_boost_campaign_deducts_from_wallet_ledger_not_just_profile(user_with_coins, own_reel, _server_keys, client_keys):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys
    balance_before = UserCoinBalance.objects.get(user=user_with_coins).balance

    response, data = _create_campaign(
        user_with_coins, own_reel, server_public_key=server_public_key,
        client_public_key=client_public_key, client_private_key=client_private_key,
    )

    assert response.status_code == 200, data
    cost = int(data['cost'])

    balance = UserCoinBalance.objects.get(user=user_with_coins)
    assert balance.balance == balance_before - cost

    user_with_coins.profile.refresh_from_db()
    assert user_with_coins.profile.coins == balance.balance


def test_create_boost_campaign_writes_a_coin_transaction_ledger_entry(user_with_coins, own_reel, _server_keys, client_keys):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys

    response, data = _create_campaign(
        user_with_coins, own_reel, server_public_key=server_public_key,
        client_public_key=client_public_key, client_private_key=client_private_key,
    )

    assert response.status_code == 200, data
    txn = CoinTransaction.objects.filter(user=user_with_coins, transaction_type='boost_campaign').first()
    assert txn is not None, 'boost purchase must appear in the coin transaction ledger'
    assert txn.coins == -int(data['cost'])


def test_create_boost_campaign_rejects_when_ledger_balance_is_insufficient(db, _server_keys, client_keys):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys

    user = User.objects.create_user(username='boost_ledger_poor_user', password='x')
    reel = Reel.objects.create(user=user, caption='cant afford this')
    try:
        # New users get a WalletConfig.welcome_bonus grant (api/signals.py)
        # -- spend it back down to a real zero balance so this test doesn't
        # depend on the welcome bonus staying below the boost cost.
        balance = UserCoinBalance.objects.get(user=user)
        if balance.balance > 0:
            balance.spend_coins(balance.balance, transaction_type='test_drain', description='drain for boost ledger test')

        # profile.coins left mismatched from the real (zero) UserCoinBalance --
        # this proves the check reads the ledger, not the legacy mirror field.
        user.profile.coins = 999999
        user.profile.save(update_fields=['coins'])

        response, data = _create_campaign(
            user, reel, server_public_key=server_public_key,
            client_public_key=client_public_key, client_private_key=client_private_key,
        )

        assert response.status_code == 400
        assert data['error'] == 'Insufficient coins'
        assert not UserCoinBalance.objects.filter(user=user, balance__gt=0).exists()
    finally:
        reel.delete()
        user.delete()
