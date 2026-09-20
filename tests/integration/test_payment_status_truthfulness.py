"""
A payment is reported as what it was.

The report: a payment that failed -- no balance, wrong PIN, cancelled on the
handset, refused by telebirr, timed out -- could still end with the customer
being shown a success message.

It was not one bug. There was no shared answer to "did this payment go
through?", so each flow decided for itself:

* ``/wallet/telebirr/query/`` reported only ``is_paid``, which makes
  ``PAY_FAILED`` and ``WAIT_PAY`` identical to a client;
* USSD coin purchases had **no status endpoint at all** -- the page polled the
  wallet and read any increase in the balance as its own purchase succeeding;
* ``CoinTransaction`` had ``is_successful`` and nothing else, so a refused
  payment and one still waiting for a callback were the same row, and neither
  could be described to anybody.

These tests cover the nine cases from the report, at the layer that decides
them. They are deliberately about two things at once, because the bug was
about the gap between them: **what the customer is told**, and **whether
anything was granted**. A test that only checked the balance would have passed
throughout the entire life of this bug.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient

from api.models.contest import CoinPackage, CoinTransaction, UserCoinBalance
from api.services import payment_status
from common.security.e2e_encryption import decrypt_payload

pytestmark = pytest.mark.django_db

WEBHOOK_URL = '/api/v1/webhooks/telebirrUssdPurchase/'
CONVERSATION = 'AG_20260920_ABCDEF0123456789'


# ── the purchase under test ──────────────────────────────────────────────────


@pytest.fixture
def buyer():
    return User.objects.create_user(username='buyer', password='x')


@pytest.fixture
def package():
    return CoinPackage.objects.create(
        name='Starter',
        price_etb=Decimal('10.00'),
        coin_amount=100,
        bonus_coins=20,
        is_active=True,
    )


@pytest.fixture
def pending_purchase(buyer, package):
    """A push sent to the handset, nothing back yet -- exactly what
    telebirr_ussd_purchase writes when telebirr accepts the request."""
    UserCoinBalance.objects.get_or_create(user=buyer)
    return CoinTransaction.objects.create(
        user=buyer,
        transaction_type='purchase',
        coins=0,
        payment_method='telebirr_ussd',
        payment_reference=CONVERSATION,
        provider_conversation_id=CONVERSATION,
        package=package,
        description='Pending USSD Push payment for Starter',
        is_successful=False,
        payment_state=payment_status.PENDING,
    )


def balance_of(user):
    row, _ = UserCoinBalance.objects.get_or_create(user=user)
    row.refresh_from_db()
    return row.balance


def result_envelope(
    *, code, desc, result_type='2', conversation=CONVERSATION, transaction_id='TX1'
):
    """A telebirr Result callback, in the SOAP shape the webhook parses."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:res="http://cps.huawei.com/cpsinterface/result">
  <soapenv:Body>
    <res:Result>
      <res:ResultType>{result_type}</res:ResultType>
      <res:ResultCode>{code}</res:ResultCode>
      <res:ResultDesc>{desc}</res:ResultDesc>
      <res:OriginatorConversationID>{conversation}</res:OriginatorConversationID>
      <res:ConversationID>CID123</res:ConversationID>
      <res:TransactionID>{transaction_id}</res:TransactionID>
    </res:Result>
  </soapenv:Body>
</soapenv:Envelope>""".encode()


def deliver(envelope):
    """The webhook, called the way telebirr calls it: no auth, text/xml."""
    return APIClient().post(WEBHOOK_URL, envelope, content_type='text/xml')


@pytest.fixture
def ask_status(encrypted_client_keys):
    """The status endpoint, as the page calls it.

    Behind ``@encrypted_endpoint``; ``encrypted_client_keys`` stands the
    server keypair up so there is a key to seal the reply with.
    """
    server_public_key, public, private = encrypted_client_keys

    def _ask(user, conversation=CONVERSATION, expect=200):
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(
            reverse('telebirr-ussd-status'),
            {'originator_conversation_id': conversation},
            HTTP_X_CLIENT_PUBLIC_KEY=public,
        )
        assert response.status_code == expect, response.status_code
        response.render()
        raw = json.loads(response.content)
        if {'encrypted', 'nonce', 'checksum'} <= raw.keys():
            raw = json.loads(
                decrypt_payload(
                    raw['encrypted'], raw['nonce'], server_public_key, raw['checksum'], private
                )
            )
        return raw

    return _ask


# ── 1. a successful payment ──────────────────────────────────────────────────


def test_a_successful_payment_is_reported_as_success_and_credits(
    buyer, pending_purchase, ask_status
):
    before = balance_of(buyer)

    deliver(
        result_envelope(code='0', result_type='0', desc='Process service request successfully.')
    )
    answer = ask_status(buyer)

    assert answer['state'] == 'SUCCESS'
    assert answer['is_final'] is True
    assert answer['coins_added'] == 120, 'the package total, bonus included'
    assert balance_of(buyer) == before + 120


def test_the_success_answer_carries_no_failure_message(buyer, pending_purchase, ask_status):
    deliver(
        result_envelope(code='0', result_type='0', desc='Process service request successfully.')
    )

    assert 'message' not in ask_status(buyer)


# ── 2-6. the ways it does not succeed ────────────────────────────────────────
#
# Each one: the state the customer is shown, and that nothing was granted.


@pytest.mark.parametrize(
    ('desc', 'expected_state', 'expected_reason'),
    [
        # 2. insufficient balance
        (
            'The balance is insufficient to complete this transaction',
            'FAILED',
            'INSUFFICIENT_BALANCE',
        ),
        # 3. wrong PIN
        ('Invalid PIN entered by customer', 'FAILED', 'WRONG_PIN'),
        # 4. user cancellation
        ('Transaction cancelled by the customer', 'CANCELLED', 'USER_CANCELLED'),
        # 5. telebirr rejection
        ('Request rejected by the service provider', 'FAILED', 'REJECTED'),
        # 6. timeout
        ('The request has timed out waiting for customer approval', 'FAILED', 'TIMEOUT'),
    ],
)
def test_a_payment_that_did_not_happen_is_never_reported_as_success(
    buyer, pending_purchase, ask_status, desc, expected_state, expected_reason
):
    before = balance_of(buyer)

    deliver(result_envelope(code='1', desc=desc))
    answer = ask_status(buyer)

    assert answer['state'] == expected_state
    assert answer['state'] != 'SUCCESS'
    assert answer['reason'] == expected_reason
    assert answer['is_final'] is True
    assert answer['coins_added'] == 0
    assert balance_of(buyer) == before, 'a failed payment moved the balance'


@pytest.mark.parametrize(
    ('desc', 'must_contain'),
    [
        ('The balance is insufficient', 'balance'),
        ('Invalid PIN entered', 'PIN'),
        ('Transaction cancelled by the customer', 'cancelled'),
        ('The request has timed out', 'expired'),
    ],
)
def test_the_customer_is_told_why(buyer, pending_purchase, ask_status, desc, must_contain):
    """A message that says what happened, not "payment failed"."""
    deliver(result_envelope(code='1', desc=desc))

    message = ask_status(buyer)['message']
    assert must_contain.lower() in message.lower(), message
    assert 'success' not in message.lower()


def test_a_failure_nobody_can_classify_is_still_a_failure(buyer, pending_purchase, ask_status):
    """The provider's wording is free text. Not recognising it costs a
    specific message -- it must never cost the failure itself."""
    deliver(result_envelope(code='77', desc='E_SOMETHING_INTERNAL_9912'))
    answer = ask_status(buyer)

    assert answer['state'] == 'FAILED'
    assert answer['reason'] == 'UNKNOWN'
    assert answer['coins_added'] == 0
    assert 'not been charged' in answer['message']


# ── 7. a pending payment ─────────────────────────────────────────────────────


def test_a_payment_with_no_callback_yet_is_pending_and_grants_nothing(
    buyer, pending_purchase, ask_status
):
    before = balance_of(buyer)

    answer = ask_status(buyer)

    assert answer['state'] == 'PENDING'
    assert answer['is_final'] is False, 'the client must keep asking'
    assert answer['coins_added'] == 0
    assert balance_of(buyer) == before


def test_pending_is_not_described_as_a_success(buyer, pending_purchase, ask_status):
    """The bug in one assertion: 'Payment received. Your coins will appear
    shortly' used to be shown with a green tick for exactly this state."""
    message = ask_status(buyer)['message']

    assert 'success' not in message.lower()
    assert 'not been charged' in message or 'not completed' in message


def test_coins_arriving_from_elsewhere_do_not_settle_the_payment(
    buyer, pending_purchase, ask_status
):
    """What made the old page wrong: it watched the wallet, so *any* credit
    during the wait read as this purchase completing. A gift is not a
    payment."""
    before = balance_of(buyer)
    UserCoinBalance.objects.get(user=buyer).add_bonus(500)
    assert balance_of(buyer) == before + 500, 'the wallet did go up'

    answer = ask_status(buyer)

    assert answer['state'] == 'PENDING', 'a credit from elsewhere settled the payment'
    assert answer['coins_added'] == 0


# ── 8. a duplicate callback ──────────────────────────────────────────────────


def test_a_success_callback_delivered_twice_credits_once(buyer, pending_purchase, ask_status):
    before = balance_of(buyer)
    envelope = result_envelope(
        code='0', result_type='0', desc='Process service request successfully.'
    )

    deliver(envelope)
    deliver(envelope)

    assert balance_of(buyer) == before + 120
    assert ask_status(buyer)['state'] == 'SUCCESS'


def test_a_failure_callback_delivered_twice_stays_one_failure(buyer, pending_purchase, ask_status):
    envelope = result_envelope(code='1', desc='The balance is insufficient')

    deliver(envelope)
    deliver(envelope)

    answer = ask_status(buyer)
    assert answer['state'] == 'FAILED'
    assert answer['reason'] == 'INSUFFICIENT_BALANCE'
    assert CoinTransaction.objects.filter(payment_reference=CONVERSATION).count() == 1


def test_a_failure_callback_cannot_undo_a_confirmed_payment(buyer, pending_purchase, ask_status):
    """Out-of-order delivery: the success is already applied and a late
    failure for the same conversation must not take the coins back or tell
    the customer their completed purchase failed."""
    deliver(
        result_envelope(code='0', result_type='0', desc='Process service request successfully.')
    )
    credited = balance_of(buyer)

    deliver(result_envelope(code='1', desc='The balance is insufficient'))

    assert ask_status(buyer)['state'] == 'SUCCESS'
    assert balance_of(buyer) == credited


# ── 9. reload during a pending payment ───────────────────────────────────────


def test_the_state_survives_a_reload(buyer, pending_purchase, ask_status):
    """Each call is a fresh client with nothing carried over -- a refreshed
    tab. The state comes back because it is on the payment, not in the page."""
    assert ask_status(buyer)['state'] == 'PENDING'
    assert ask_status(buyer)['state'] == 'PENDING'

    deliver(result_envelope(code='1', desc='Invalid PIN entered'))

    assert ask_status(buyer)['state'] == 'FAILED'
    assert ask_status(buyer)['reason'] == 'WRONG_PIN'


def test_a_purchase_confirmed_between_polls_is_still_found(buyer, pending_purchase, ask_status):
    """Crediting rewrites payment_reference to telebirr's transaction id, so
    the row is no longer under the conversation id the page is polling. If
    that lookup missed, a successful purchase would read as 'not found' on the
    very next poll."""
    deliver(
        result_envelope(
            code='0',
            result_type='0',
            desc='Process service request successfully.',
            transaction_id='EBT0987654321',
        )
    )

    answer = ask_status(buyer)
    assert answer['state'] == 'SUCCESS'
    assert answer['coins_added'] == 120


# ── the endpoint is not a lookup key for other people's payments ─────────────


def test_somebody_elses_purchase_is_not_visible(buyer, pending_purchase, ask_status):
    stranger = User.objects.create_user(username='stranger', password='x')

    ask_status(stranger, expect=404)


def test_an_unknown_conversation_is_not_invented(buyer, pending_purchase, ask_status):
    ask_status(buyer, conversation='AG_NOTHING_HERE', expect=404)
