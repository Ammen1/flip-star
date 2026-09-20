"""
Turning what telebirr said into what the customer is told.

The integration tests drive the endpoints; these pin the mapping underneath
them, including the cases that are awkward to reach through a webhook -- the
statuses this code has never seen, and the two directions the mapping can be
wrong in.

Both directions matter, and only one of them was reported:

* calling a failure a success takes somebody's money in their mind and gives
  them nothing -- the reported bug;
* calling a success, or something still in flight, a failure sends somebody to
  pay twice.

So an unrecognised status is PENDING. Not FAILED, not SUCCESS: unknown is a
state we have, and it is the only honest answer.
"""

from __future__ import annotations

import pytest

from api.services.payment_status import (
    CANCELLED,
    FAILED,
    INSUFFICIENT_BALANCE,
    PENDING,
    REJECTED,
    SUCCESS,
    TIMEOUT,
    UNKNOWN,
    USER_CANCELLED,
    WRONG_PIN,
    classify_reason,
    from_h5_order,
    from_ussd_result,
    grants_value,
    is_terminal,
    payload,
    reason_message,
)

# ── the states themselves ────────────────────────────────────────────────────


def test_only_success_pays_out():
    """The rule the whole issue turns on, in one function."""
    assert grants_value(SUCCESS) is True
    for state in (FAILED, PENDING, CANCELLED):
        assert grants_value(state) is False, f'{state} would have granted coins'


def test_pending_is_not_terminal():
    """A client must keep asking, and must not draw a conclusion yet."""
    assert is_terminal(PENDING) is False
    assert is_terminal(SUCCESS) is True
    assert is_terminal(FAILED) is True
    assert is_terminal(CANCELLED) is True


# ── USSD Push results ────────────────────────────────────────────────────────


def test_the_documented_success_is_the_only_success():
    assert from_ussd_result('0', '0') == (SUCCESS, None)


@pytest.mark.parametrize(
    ('code', 'rtype'),
    [('1', '2'), ('0', '2'), ('1', '0'), ('2001', '1'), ('', ''), (None, None)],
)
def test_anything_else_is_not_a_success(code, rtype):
    state, _ = from_ussd_result(code, rtype)
    assert state != SUCCESS


def test_a_cancellation_is_reported_as_a_cancellation():
    """'You cancelled it' and 'it failed' are different things to be told."""
    state, reason = from_ussd_result('1', '2', 'Transaction cancelled by the customer')
    assert (state, reason) == (CANCELLED, USER_CANCELLED)


@pytest.mark.parametrize(
    ('desc', 'expected'),
    [
        ('The balance is insufficient for this transaction', INSUFFICIENT_BALANCE),
        ('Customer has not enough money', INSUFFICIENT_BALANCE),
        ('Invalid PIN', WRONG_PIN),
        ('Wrong password supplied', WRONG_PIN),
        ('Request timed out', TIMEOUT),
        ('The session has expired', TIMEOUT),
        ('Rejected by the provider', REJECTED),
        ('Payment declined', REJECTED),
    ],
)
def test_the_reason_is_read_from_what_the_provider_said(desc, expected):
    assert classify_reason(desc) == expected


def test_a_description_nobody_can_read_is_still_a_failure():
    state, reason = from_ussd_result('9999', '2', 'E_INTERNAL_4412')
    assert state == FAILED
    assert reason == UNKNOWN


def test_no_description_at_all_is_still_a_failure():
    state, reason = from_ussd_result('9999', '2', None)
    assert state == FAILED
    assert reason == UNKNOWN


def test_every_reason_has_something_to_say():
    for reason in (INSUFFICIENT_BALANCE, WRONG_PIN, USER_CANCELLED, REJECTED, TIMEOUT, UNKNOWN):
        message = reason_message(reason)
        # Not a capitalisation check: 'telebirr' is lower case everywhere in
        # this product, including at the start of a sentence.
        assert message.strip(), f'{reason} has no message'
        assert message.endswith('.'), f'{reason} is not a sentence: {message}'
        assert 'success' not in message.lower(), f'{reason} reads as a success'


def test_an_unrecognised_reason_still_gets_a_message():
    assert reason_message('SOMETHING_NEW') == reason_message(UNKNOWN)
    assert reason_message(None) == reason_message(UNKNOWN)


# ── H5 / SuperApp checkout ───────────────────────────────────────────────────


@pytest.mark.parametrize('status', ['PAY_SUCCESS', 'pay_success', ' PAY_SUCCESS '])
def test_a_paid_order_is_a_success(status):
    assert from_h5_order(order_status=status)[0] == SUCCESS


def test_a_failed_order_is_a_failure_not_a_pending():
    """This is the bug at its source: PAY_FAILED and WAIT_PAY were both
    'not is_paid', and the client turned 'not is_paid' into 'pending', and
    the page drew pending as a success."""
    assert from_h5_order(order_status='PAY_FAILED')[0] == FAILED
    assert from_h5_order(order_status='WAIT_PAY')[0] == PENDING


def test_a_closed_order_reads_as_cancelled():
    assert from_h5_order(order_status='CLOSED') == (CANCELLED, USER_CANCELLED)


def test_an_unknown_order_status_waits_rather_than_guessing():
    """Inventing a terminal state for a status never seen is how a pending
    payment comes to be announced as failed."""
    assert from_h5_order(order_status='SOMETHING_NEW') == (PENDING, None)
    assert from_h5_order() == (PENDING, None)


def test_the_notify_status_is_understood_too():
    """The async notify carries trade_status, not order_status."""
    assert from_h5_order(trade_status='Completed')[0] == SUCCESS
    assert from_h5_order(trade_status='Failed')[0] == FAILED


def test_order_status_wins_over_trade_status():
    """queryOrder is the authoritative read; the notify is a nudge."""
    assert from_h5_order(order_status='PAY_SUCCESS', trade_status='Failed')[0] == SUCCESS


def test_the_providers_wording_sharpens_a_failure():
    state, reason = from_h5_order(order_status='PAY_FAILED', description='Insufficient balance')
    assert state == FAILED
    assert reason == INSUFFICIENT_BALANCE


def test_wording_cannot_turn_a_success_into_a_failure():
    """A description is only ever allowed to refine why something failed."""
    state, reason = from_h5_order(order_status='PAY_SUCCESS', description='cancelled')
    assert state == SUCCESS
    assert reason is None


# ── what goes on the wire ────────────────────────────────────────────────────


def test_the_payload_tells_a_client_everything_it_needs():
    body = payload(FAILED, INSUFFICIENT_BALANCE, coins_added=0)

    assert body['state'] == FAILED
    assert body['is_final'] is True
    assert body['reason'] == INSUFFICIENT_BALANCE
    assert 'balance' in body['message']
    assert body['coins_added'] == 0


def test_a_pending_payload_says_it_is_not_final():
    body = payload(PENDING)

    assert body['is_final'] is False
    assert 'success' not in body['message'].lower()


def test_a_success_payload_carries_no_failure_message():
    """A client that renders `message` whenever it is present must not find
    apologetic copy under a green tick."""
    assert 'message' not in payload(SUCCESS)
