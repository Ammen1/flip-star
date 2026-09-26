"""
Regression tests for Telebirr B2C withdrawal payouts -- ported from the
master branch, missing entirely in the current project before this change
(WithdrawalRequest had no B2C linkage fields, TelebirrDirectDebitService had
no initiate_b2c_payment, and there was no telebirr_b2c_webhook).

The central requirement being tested: a withdrawal must never be marked
'completed' before Telebirr actually confirms the payout. request_withdrawal
only ever moves a Telebirr withdrawal from 'pending' to 'processing' (on
successful B2C *initiation*) or 'failed' (refunding points); only
telebirr_b2c_webhook, once Telebirr's own callback arrives, moves it to
'completed'.

Unlike master's webhook (no locking at all), this uses select_for_update()
+ transaction.atomic() throughout, matching the rest of this codebase's
Telebirr-adjacent webhooks -- see api/views/direct_debit.py::telebirr_b2c_webhook
and telebirr_direct_debit_webhook for the established pattern.

Uses the real `db` fixture -- the 0063_add_mentions migration dependency bug
that used to force MIGRATIONS_ARE_REPLAYABLE = False has been fixed (see
tests/conftest.py). request_withdrawal is also gated by @encrypted_endpoint
(a real Tier-1 sensitive-endpoint requirement, not a test artifact -- see
tests/unit/test_encrypted_endpoints_wiring.py), so it is exercised through a
real encrypted round trip rather than bypassed, following the exact pattern
in tests/unit/test_encrypted_transport.py::test_full_round_trip_function_based_view.
telebirr_b2c_webhook is AllowAny and unencrypted (Telebirr posts raw SOAP
XML, not an encrypted envelope), so those tests call it directly.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import fakeredis
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.direct_debit import B2CPaymentTransaction
from api.models.wallet import WalletConfig, WithdrawalRequest
from api.views.direct_debit import initiate_b2c_payment, list_b2c_payments, telebirr_b2c_webhook
from api.views.wallet import request_withdrawal
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
        plaintext_dict,
        receiver_public_key_b64=receiver_public_key,
        sender_private_key_b64=sender_private_key,
    )
    return sealed.to_dict()


def _decrypt_response(response, *, server_public_key, client_private_key):
    response.render()
    envelope_out = json.loads(response.content)
    plaintext = decrypt_payload(
        envelope_out['encrypted'],
        envelope_out['nonce'],
        server_public_key,
        envelope_out['checksum'],
        client_private_key,
    )
    return json.loads(plaintext)


@pytest.fixture
def user(db):
    u = User.objects.create_user(username='b2c_user', password='x', email='b2c@example.com')
    u.profile.phone_number = '0911223344'
    u.profile.points = 5000
    u.profile.save()
    WalletConfig.get_config()
    yield u
    u.delete()


def _call_request_withdrawal(
    user, body, *, server_public_key, client_public_key, client_private_key
):
    envelope = _encrypted_envelope(
        body, sender_private_key=client_private_key, receiver_public_key=server_public_key
    )
    request = factory.post(
        '/wallet/withdraw/',
        data=json.dumps(envelope),
        content_type='application/json',
        HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
    )
    force_authenticate(request, user=user)
    response = request_withdrawal(request)
    return _decrypt_response(
        response, server_public_key=server_public_key, client_private_key=client_private_key
    )


# ---------------------------------------------------------------------------
# request_withdrawal: B2C initiation, never marks completed
# ---------------------------------------------------------------------------


def test_successful_b2c_initiation_moves_withdrawal_to_processing_never_completed(
    user, _server_keys, client_keys
):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys

    with patch(
        'api.views.wallet.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value={
            'success': True,
            'originator_conversation_id': 'S_X20260820TEST1',
            'conversation_id': 'AG_20260820TEST1',
        },
    ):
        data = _call_request_withdrawal(
            user,
            {'point_amount': 2000, 'payout_method': 'telebirr'},
            server_public_key=server_public_key,
            client_public_key=client_public_key,
            client_private_key=client_private_key,
        )

    assert data['withdrawal']['status'] == 'processing'
    withdrawal = WithdrawalRequest.objects.get(user=user)
    assert withdrawal.status == 'processing'
    assert withdrawal.status != 'completed'
    assert withdrawal.originator_conversation_id == 'S_X20260820TEST1'
    assert withdrawal.conversation_id == 'AG_20260820TEST1'

    user.profile.refresh_from_db()
    assert user.profile.points == 3000


def test_failed_b2c_initiation_marks_failed_and_refunds_points(user, _server_keys, client_keys):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys

    with patch(
        'api.views.wallet.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value={'success': False, 'error': 'HTTP 500: upstream error'},
    ):
        envelope = _encrypted_envelope(
            {'point_amount': 2000, 'payout_method': 'telebirr'},
            sender_private_key=client_private_key,
            receiver_public_key=server_public_key,
        )
        request = factory.post(
            '/wallet/withdraw/',
            data=json.dumps(envelope),
            content_type='application/json',
            HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
        )
        force_authenticate(request, user=user)
        response = request_withdrawal(request)
        response.render()
        assert response.status_code == 400

        data = _decrypt_response(
            response, server_public_key=server_public_key, client_private_key=client_private_key
        )

    assert data['error'] == 'B2C payment initiation failed'
    withdrawal = WithdrawalRequest.objects.get(user=user)
    assert withdrawal.status == 'failed'
    assert withdrawal.status != 'completed'

    user.profile.refresh_from_db()
    assert (
        user.profile.points == 5000
    ), 'points must be fully refunded after a failed B2C initiation'


def test_non_telebirr_payout_method_never_calls_b2c_and_stays_pending(
    user, _server_keys, client_keys
):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys

    with patch('api.views.wallet.telebirr_direct_debit_service.initiate_b2c_payment') as mock_b2c:
        data = _call_request_withdrawal(
            user,
            {
                'point_amount': 2000,
                'payout_method': 'bank_transfer',
                'payout_account': '1000123456789',
                'payout_account_name': 'Test User',
            },
            server_public_key=server_public_key,
            client_public_key=client_public_key,
            client_private_key=client_private_key,
        )

    mock_b2c.assert_not_called()
    assert data['withdrawal']['status'] == 'pending'


# ---------------------------------------------------------------------------
# telebirr_b2c_webhook: withdrawal-direct correlation path
# ---------------------------------------------------------------------------


@pytest.fixture
def processing_withdrawal(db):
    u = User.objects.create_user(username='b2c_webhook_user', password='x')
    u.profile.points = 3000
    u.profile.points_withdrawn_total = 2000
    u.profile.save()
    withdrawal = WithdrawalRequest.objects.create(
        user=u,
        point_amount=2000,
        gross_birr=200,
        fee_birr=40,
        net_birr=160,
        conversion_rate=10,
        payout_method='telebirr',
        payout_account='251911223344',
        status='processing',
        originator_conversation_id='S_X20260820WEBHOOK1',
    )
    yield withdrawal
    withdrawal.delete()
    u.delete()


def _soap_result(*, originator_conversation_id, result_code, transaction_id='', result_desc=''):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:res="http://cps.huawei.com/cpsinterface/response">
  <soapenv:Body>
    <api:Result xmlns:api="http://cps.huawei.com/cpsinterface/response">
      <res:ResultType>0</res:ResultType>
      <res:ResultCode>{result_code}</res:ResultCode>
      <res:ResultDesc>{result_desc}</res:ResultDesc>
      <res:OriginatorConversationID>{originator_conversation_id}</res:OriginatorConversationID>
      <res:TransactionID>{transaction_id}</res:TransactionID>
    </api:Result>
  </soapenv:Body>
</soapenv:Envelope>""".encode()


def test_webhook_success_marks_withdrawal_completed(processing_withdrawal):
    body = _soap_result(
        originator_conversation_id='S_X20260820WEBHOOK1',
        result_code='0',
        transaction_id='TXN123',
    )
    request = factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml')

    response = telebirr_b2c_webhook(request)

    assert response.status_code == 200
    processing_withdrawal.refresh_from_db()
    assert processing_withdrawal.status == 'completed'
    assert processing_withdrawal.completed_at is not None
    assert processing_withdrawal.payout_reference == 'TXN123'


def test_webhook_failure_marks_failed_and_refunds_points(processing_withdrawal):
    body = _soap_result(
        originator_conversation_id='S_X20260820WEBHOOK1',
        result_code='1',
        result_desc='Insufficient funds',
    )
    request = factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml')

    response = telebirr_b2c_webhook(request)

    assert response.status_code == 200
    processing_withdrawal.refresh_from_db()
    assert processing_withdrawal.status == 'failed'
    assert 'Insufficient funds' in processing_withdrawal.rejection_reason

    processing_withdrawal.user.profile.refresh_from_db()
    assert processing_withdrawal.user.profile.points == 5000


def test_webhook_duplicate_delivery_does_not_double_process(processing_withdrawal):
    body = _soap_result(
        originator_conversation_id='S_X20260820WEBHOOK1',
        result_code='0',
        transaction_id='TXN123',
    )

    telebirr_b2c_webhook(factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml'))
    telebirr_b2c_webhook(factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml'))

    processing_withdrawal.refresh_from_db()
    assert processing_withdrawal.status == 'completed'


def test_webhook_duplicate_failure_does_not_double_refund(processing_withdrawal):
    body = _soap_result(
        originator_conversation_id='S_X20260820WEBHOOK1', result_code='1', result_desc='fail'
    )

    telebirr_b2c_webhook(factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml'))
    telebirr_b2c_webhook(factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml'))

    processing_withdrawal.user.profile.refresh_from_db()
    assert processing_withdrawal.user.profile.points == 5000, 'points must only be refunded once'


def test_webhook_ignores_unknown_originator_conversation_id():
    body = _soap_result(
        originator_conversation_id='S_X_NOT_A_REAL_ONE', result_code='0', transaction_id='TXN999'
    )
    request = factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml')

    response = telebirr_b2c_webhook(request)

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# telebirr_b2c_webhook: standalone B2CPaymentTransaction correlation path
# ---------------------------------------------------------------------------


@pytest.fixture
def standalone_transaction(db):
    u = User.objects.create_user(username='b2c_standalone_user', password='x')
    txn = B2CPaymentTransaction.objects.create(
        payer=u,
        receiver_msisdn='251911223344',
        amount=100,
        reason_type='Bonus payout',
        originator_conversation_id='S_X20260820STANDALONE1',
        status='pending',
    )
    yield txn
    txn.delete()
    u.delete()


def test_webhook_marks_standalone_transaction_success(standalone_transaction):
    body = _soap_result(
        originator_conversation_id='S_X20260820STANDALONE1',
        result_code='0',
        transaction_id='TXN456',
    )
    request = factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml')

    telebirr_b2c_webhook(request)

    standalone_transaction.refresh_from_db()
    assert standalone_transaction.status == 'success'
    assert standalone_transaction.telebirr_transaction_id == 'TXN456'


def test_webhook_standalone_transaction_also_completes_linked_withdrawal(standalone_transaction):
    withdrawal = WithdrawalRequest.objects.create(
        user=standalone_transaction.payer,
        point_amount=1000,
        gross_birr=100,
        fee_birr=20,
        net_birr=80,
        conversion_rate=10,
        payout_method='telebirr',
        payout_account='251911223344',
        status='processing',
    )
    standalone_transaction.reference_data = {'withdrawal_id': str(withdrawal.id)}
    standalone_transaction.save(update_fields=['reference_data'])

    body = _soap_result(
        originator_conversation_id='S_X20260820STANDALONE1',
        result_code='0',
        transaction_id='TXN789',
    )
    telebirr_b2c_webhook(factory.post('/webhooks/telebirrB2C/', data=body, content_type='text/xml'))

    withdrawal.refresh_from_db()
    assert withdrawal.status == 'completed'
    assert withdrawal.telebirr_transaction_id == 'TXN789'

    withdrawal.delete()


# ---------------------------------------------------------------------------
# initiate_b2c_payment / list_b2c_payments (standalone, non-withdrawal use)
# ---------------------------------------------------------------------------


def test_initiate_b2c_payment_creates_transaction_record(user):
    with patch(
        'api.views.direct_debit.telebirr_direct_debit_service.initiate_b2c_payment',
        return_value={
            'success': True,
            'originator_conversation_id': 'S_X20260820STANDALONE9',
            'conversation_id': 'AG_20260820STANDALONE9',
        },
    ):
        request = factory.post(
            '/telebirr/b2c/initiate/',
            {
                'receiver_msisdn': '251911223344',
                'amount': '150.00',
                'reason_type': 'Bonus',
            },
            format='json',
        )
        force_authenticate(request, user=user)

        response = initiate_b2c_payment(request)

    assert response.status_code == 201, response.data
    assert response.data['success'] is True
    txn = B2CPaymentTransaction.objects.get(payer=user)
    assert txn.status == 'pending'
    assert txn.originator_conversation_id == 'S_X20260820STANDALONE9'


def test_initiate_b2c_payment_rejects_invalid_amount(user):
    request = factory.post(
        '/telebirr/b2c/initiate/',
        {
            'receiver_msisdn': '251911223344',
            'amount': '-5.00',
        },
        format='json',
    )
    force_authenticate(request, user=user)

    response = initiate_b2c_payment(request)

    assert response.status_code == 400
    assert not B2CPaymentTransaction.objects.filter(payer=user).exists()


def test_list_b2c_payments_only_returns_the_caller_own_transactions(user):
    other = User.objects.create_user(username='b2c_other_payer', password='x')
    try:
        B2CPaymentTransaction.objects.create(
            payer=user, receiver_msisdn='251911111111', amount=10, reason_type='x'
        )
        B2CPaymentTransaction.objects.create(
            payer=other, receiver_msisdn='251922222222', amount=20, reason_type='x'
        )

        request = factory.get('/telebirr/b2c/payments/')
        force_authenticate(request, user=user)

        response = list_b2c_payments(request)

        assert response.status_code == 200
        assert len(response.data['transactions']) == 1
        assert response.data['transactions'][0]['receiver_msisdn'] == '251911111111'
    finally:
        other.delete()


# ── Ethio Telecom's reference envelope ──────────────────────────────────────
#
# Their sample cashout request carries a ReferenceData block that ours did not,
# which is what the gateway answered with `1002 Parameter is incorrect`. These
# pin the three things that sample settled.


def _sent_envelope(**kwargs):
    """The SOAP body initiate_b2c_payment actually transmits."""
    from unittest.mock import patch

    from api.integrations.telebirr.direct_debit import TelebirrDirectDebitService

    captured = {}

    class _Response:
        status_code = 200
        text = '<res:ResponseCode>0</res:ResponseCode>'

    def _capture(url, data=None, headers=None, **rest):
        captured['body'] = data
        captured['action'] = (headers or {}).get('SOAPAction')
        return _Response()

    with patch('api.integrations.telebirr.direct_debit.requests.post', _capture):
        TelebirrDirectDebitService().initiate_b2c_payment(
            receiver_msisdn='251911227833', amount='1.00', **kwargs
        )
    return captured


def test_a_remark_is_sent_as_reference_data():
    """`remark` was accepted, documented, and then dropped on the floor.

    Ethio Telecom's sample shows where it belongs: a ReferenceData item keyed
    'Remarks'. Without the block the gateway rejects the request outright.
    """
    sent = _sent_envelope(remark='AddisTest1')

    assert '<req:ReferenceData>' in sent['body']
    assert '<com:Key>Remarks</com:Key>' in sent['body']
    assert '<com:Value>AddisTest1</com:Value>' in sent['body']


def test_reference_data_is_omitted_rather_than_sent_empty():
    """An empty element is a value, and this endpoint rejects values it
    dislikes -- so no remark means no block at all."""
    assert '<req:ReferenceData>' not in _sent_envelope()['body']


def test_the_envelope_is_well_formed_xml():
    """It is built by string interpolation, so nothing else checks this."""
    from defusedxml.minidom import parseString

    parseString(_sent_envelope(remark='x')['body'])


def test_the_command_id_is_the_service_code_telebirr_named():
    """InitTrans_2003, from their reference envelope. The old default was
    53906 -- a copy of the short code B2C used before 553559, which made a
    coincidence look deliberate."""
    sent = _sent_envelope()

    assert sent['action'] == 'InitTrans_2003'
    assert '<req:CommandID>InitTrans_2003</req:CommandID>' in sent['body']


def test_two_requests_in_the_same_second_get_different_conversation_ids():
    """The one that could pay the wrong person.

    telebirr_b2c_webhook correlates a payout result by looking up
    originator_conversation_id. The id was `S_X` plus a second-resolution
    timestamp, so two payouts in one second shared it and a result for either
    could settle the other.
    """
    from api.integrations.telebirr.direct_debit import TelebirrDirectDebitService

    svc = TelebirrDirectDebitService()
    ids = {svc._generate_originator_conversation_id() for _ in range(500)}

    assert len(ids) == 500


def test_the_conversation_id_keeps_the_prefix_the_gateway_accepts():
    """Entropy was appended rather than replacing the format: `S_X` plus a
    timestamp is known-accepted, and this is not the change to gamble on."""
    from api.integrations.telebirr.direct_debit import TelebirrDirectDebitService

    generated = TelebirrDirectDebitService()._generate_originator_conversation_id()

    assert generated.startswith('S_X')
    assert len(generated) > len('S_X20260926113518')
