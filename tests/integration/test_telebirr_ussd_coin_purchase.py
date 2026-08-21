"""
Regression tests for the Telebirr SuperApp/USSD coin-purchase flow
(api/views/wallet.py: telebirr_auth, telebirr_query_order,
telebirr_ussd_purchase, telebirr_ussd_webhook) -- ported from the master
branch, missing entirely in the current project before this change.
Parallel to the existing H5/InApp flow (telebirr_initiate_payment/
telebirr_callback), sharing the same CoinTransaction/UserCoinBalance
crediting shape but keyed by originator_conversation_id and
payment_method='telebirr_ussd' instead of merch_order_id/'telebirr'.

Master's telebirr_ussd_webhook credits coins with no locking at all --
a directly-exploitable double-credit if Telebirr retries the webhook
(documented behavior for this gateway). The ported version reuses the
locked, idempotent single-row pattern already established for the H5 flow's
_credit_telebirr_order (api/views/wallet.py) via a new
_credit_telebirr_ussd_order helper -- see the double-delivery test below.

telebirr_ussd_purchase is gated by @encrypted_endpoint (matching its H5
sibling, telebirr_initiate_payment) and exercised through a real encrypted
round trip, following the pattern in tests/integration/test_boost_wallet_ledger.py.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import fakeredis
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.contest import CoinPackage, CoinTransaction, UserCoinBalance
from api.views.wallet import (
    telebirr_auth,
    telebirr_query_order,
    telebirr_ussd_purchase,
    telebirr_ussd_webhook,
)
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


def _decrypt_response(response, *, server_public_key, client_private_key):
    response.render()
    envelope_out = json.loads(response.content)
    plaintext = decrypt_payload(
        envelope_out['encrypted'], envelope_out['nonce'], server_public_key,
        envelope_out['checksum'], client_private_key,
    )
    return json.loads(plaintext)


@pytest.fixture
def package(db):
    pkg = CoinPackage.objects.create(name='USSD Test Pack', price_etb=50, coin_amount=500, bonus_coins=50)
    yield pkg
    pkg.delete()


@pytest.fixture
def user_with_phone(db):
    u = User.objects.create_user(username='ussd_purchase_user', password='x')
    u.profile.phone_number = '251911000222'
    u.profile.save()
    yield u
    u.delete()


def test_telebirr_ussd_purchase_creates_pending_transaction(user_with_phone, package, _server_keys, client_keys):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys

    with patch(
        'api.views.wallet.telebirr_direct_debit_service.initiate_ussd_push_payment',
        return_value={'success': True, 'originator_conversation_id': 'S_X1', 'conversation_id': 'AG_1', 'message': 'Accepted'},
    ) as mock_initiate:
        envelope = encrypt_payload(
            {'package_id': package.id}, receiver_public_key_b64=server_public_key, sender_private_key_b64=client_private_key,
        ).to_dict()
        request = factory.post(
            '/wallet/telebirrUssdPurchase/', data=json.dumps(envelope), content_type='application/json',
            HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
        )
        force_authenticate(request, user=user_with_phone)

        response = telebirr_ussd_purchase(request)

    data = _decrypt_response(response, server_public_key=server_public_key, client_private_key=client_private_key)
    assert response.status_code == 200, data
    assert data['originator_conversation_id'] == 'S_X1'
    mock_initiate.assert_called_once()

    txn = CoinTransaction.objects.get(user=user_with_phone, payment_method='telebirr_ussd')
    assert txn.is_successful is False
    assert txn.payment_reference == 'S_X1'


def test_telebirr_ussd_purchase_rejects_unknown_package(user_with_phone, db, _server_keys, client_keys):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys

    envelope = encrypt_payload(
        {'package_id': 999999}, receiver_public_key_b64=server_public_key, sender_private_key_b64=client_private_key,
    ).to_dict()
    request = factory.post(
        '/wallet/telebirrUssdPurchase/', data=json.dumps(envelope), content_type='application/json',
        HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
    )
    force_authenticate(request, user=user_with_phone)

    response = telebirr_ussd_purchase(request)

    assert response.status_code == 404


def _ussd_soap_result(*, originator_conversation_id, result_code, transaction_id='', result_desc=''):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:res="http://cps.huawei.com/cpsinterface/result">
  <soapenv:Body>
    <api:Result xmlns:api="http://cps.huawei.com/cpsinterface/api_resultmgr">
      <res:ResultType>0</res:ResultType>
      <res:ResultCode>{result_code}</res:ResultCode>
      <res:ResultDesc>{result_desc}</res:ResultDesc>
      <res:OriginatorConversationID>{originator_conversation_id}</res:OriginatorConversationID>
      <res:TransactionID>{transaction_id}</res:TransactionID>
    </api:Result>
  </soapenv:Body>
</soapenv:Envelope>'''.encode()


@pytest.fixture
def pending_ussd_transaction(db, user_with_phone, package):
    txn = CoinTransaction.objects.create(
        user=user_with_phone, transaction_type='purchase', coins=0, payment_method='telebirr_ussd',
        payment_reference='S_USSD1', package=package, description='Pending USSD Push payment', is_successful=False,
    )
    yield txn


def test_telebirr_ussd_webhook_credits_coins_on_success(pending_ussd_transaction, user_with_phone, package):
    body = _ussd_soap_result(originator_conversation_id='S_USSD1', result_code='0', transaction_id='TX123')
    request = factory.post('/webhooks/telebirrUssdPurchase/', data=body, content_type='text/xml')

    response = telebirr_ussd_webhook(request)

    assert response.status_code == 200, response.data
    assert response.data['coins_added'] == package.get_total_coins()

    pending_ussd_transaction.refresh_from_db()
    assert pending_ussd_transaction.is_successful is True
    assert pending_ussd_transaction.coins == package.get_total_coins()

    balance = UserCoinBalance.objects.get(user=user_with_phone)
    assert balance.telebirr_purchased_balance == package.get_total_coins()


def test_telebirr_ussd_webhook_is_idempotent_against_duplicate_delivery(pending_ussd_transaction, user_with_phone, package):
    """Telebirr is documented to retry webhook delivery. Master credits coins
    with no locking at all -- a duplicate delivery double-credits the same
    payment. This must not double-credit."""
    body = _ussd_soap_result(originator_conversation_id='S_USSD1', result_code='0', transaction_id='TX123')

    first = telebirr_ussd_webhook(factory.post('/webhooks/telebirrUssdPurchase/', data=body, content_type='text/xml'))
    second = telebirr_ussd_webhook(factory.post('/webhooks/telebirrUssdPurchase/', data=body, content_type='text/xml'))

    assert first.status_code == 200
    assert first.data.get('coins_added') == package.get_total_coins()
    assert second.status_code == 200
    assert second.data.get('coins_added') is None

    balance = UserCoinBalance.objects.get(user=user_with_phone)
    assert balance.telebirr_purchased_balance == package.get_total_coins()
    assert CoinTransaction.objects.filter(payment_reference__in=('S_USSD1', 'TX123'), payment_method='telebirr_ussd').count() == 1


def test_telebirr_ussd_webhook_marks_failed_payment(pending_ussd_transaction, package):
    body = _ussd_soap_result(originator_conversation_id='S_USSD1', result_code='1', result_desc='Insufficient funds')
    request = factory.post('/webhooks/telebirrUssdPurchase/', data=body, content_type='text/xml')

    response = telebirr_ussd_webhook(request)

    assert response.status_code == 200
    pending_ussd_transaction.refresh_from_db()
    assert pending_ussd_transaction.is_successful is False
    assert 'Insufficient funds' in pending_ussd_transaction.description


def test_telebirr_query_order_credits_coins_when_paid(db):
    user = User.objects.create_user(username='ussd_query_user', password='x')
    package = CoinPackage.objects.create(name='Query Test Pack', price_etb=20, coin_amount=200)
    txn = CoinTransaction.objects.create(
        user=user, transaction_type='purchase', coins=0, payment_method='telebirr',
        payment_reference='M123', package=package, description='pending', is_successful=False,
    )
    try:
        with patch(
            'api.views.wallet.telebirr_service.query_order',
            return_value={'success': True, 'is_paid': True, 'trade_status': 'TRADE_SUCCESS', 'payment_order_id': 'P123'},
        ):
            request = factory.get('/wallet/telebirr/query/?merch_order_id=M123')
            force_authenticate(request, user=user)

            response = telebirr_query_order(request)

        assert response.status_code == 200, response.data
        assert response.data['coins_added'] == package.get_total_coins()
        txn.refresh_from_db()
        assert txn.is_successful is True
    finally:
        txn.delete()
        package.delete()
        user.delete()


def test_telebirr_auth_logs_in_existing_user_by_phone(db):
    user = User.objects.create_user(username='superapp_existing', password='x')
    user.profile.phone_number = '251933000111'
    user.profile.save()
    try:
        with patch(
            'api.views.wallet.telebirr_service.request_auth_token',
            return_value={'success': True, 'identifier': '251933000111', 'open_id': 'oid1', 'nickName': 'Abebe'},
        ):
            request = factory.post('/wallet/telebirr/auth/', {'access_token': 'tok123'}, format='json')

            response = telebirr_auth(request)

        assert response.status_code == 200, response.data
        assert response.data['user']['username'] == 'superapp_existing'
        assert 'token' in response.data
    finally:
        user.delete()


def test_telebirr_auth_creates_minimal_account_for_new_phone(db):
    with patch(
        'api.views.wallet.telebirr_service.request_auth_token',
        return_value={'success': True, 'identifier': '251944000222', 'open_id': 'oid2', 'nickName': 'New'},
    ):
        request = factory.post('/wallet/telebirr/auth/', {'access_token': 'tok456'}, format='json')

        response = telebirr_auth(request)

    try:
        assert response.status_code == 401
        assert response.data['requires_subscription'] is True
        assert response.data['is_new_user'] is True
        assert User.objects.filter(username='251944000222').exists()
    finally:
        User.objects.filter(username='251944000222').delete()


def test_telebirr_auth_rejects_missing_access_token(db):
    request = factory.post('/wallet/telebirr/auth/', {}, format='json')

    response = telebirr_auth(request)

    assert response.status_code == 400


def test_telebirr_auth_rejects_failed_telebirr_exchange(db):
    with patch(
        'api.views.wallet.telebirr_service.request_auth_token',
        return_value={'success': False, 'error': 'Invalid token'},
    ):
        request = factory.post('/wallet/telebirr/auth/', {'access_token': 'bad'}, format='json')

        response = telebirr_auth(request)

    assert response.status_code == 400
