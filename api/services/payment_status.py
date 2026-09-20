"""
What a payment's state is, in one vocabulary, for every flow.

The reported fault: a payment that failed -- no balance, wrong PIN, cancelled
on the handset, refused by telebirr, timed out -- could still end with the
customer being told it succeeded. It was not one bug. It was the absence of a
shared answer to "did this payment go through?", so each flow guessed:

* the SuperApp bridge returned ``success: true, pending: true`` for a payment
  the server had marked **failed**, and the pages render anything ``success``
  as a green tick;
* the coin page never asked about the payment at all -- it polled the wallet
  and called any increase in the balance a successful purchase, so a gift
  arriving during the wait read as "Payment successful!";
* ``/wallet/telebirr/query/`` reported only ``is_paid``, which makes PAY_FAILED
  and WAIT_PAY identical to a client;
* ``CoinTransaction`` had ``is_successful`` and nothing else, so a failed
  purchase and one still waiting for a callback were the same row.

So this module defines the states, and everything that reports a payment --
the H5 query, the USSD status endpoint, the subscription query, the webhooks --
maps into them here rather than inventing its own.

The states are deliberately few, and the distinction that matters is
*terminal* versus not: a PENDING payment grants nothing and must never be
shown as success, and only SUCCESS may move a balance.

No code table is invented. Telebirr documents ``ResultCode 0`` /
``ResultType 0`` as acceptance and ``order_status`` for the checkout API;
beyond that, failures arrive as prose in ``ResultDesc``. What can be read from
that prose confidently is read; everything else is an honest generic failure
rather than a guess that would put wrong words in front of a customer.
"""

from __future__ import annotations

import re

# ── the states ───────────────────────────────────────────────────────────────

SUCCESS = 'SUCCESS'
FAILED = 'FAILED'
PENDING = 'PENDING'
CANCELLED = 'CANCELLED'

STATES = (SUCCESS, FAILED, PENDING, CANCELLED)

#: States that will not change again. A payment outside this set is still in
#: flight: nothing may be granted for it and nothing may be reported about it
#: except that it is waiting.
TERMINAL_STATES = (SUCCESS, FAILED, CANCELLED)


def is_terminal(state: str) -> bool:
    return state in TERMINAL_STATES


def grants_value(state: str) -> bool:
    """Whether this state may move a wallet balance or open access.

    One function so the rule cannot be written differently in two places:
    only a confirmed success pays out.
    """
    return state == SUCCESS


# ── why it did not succeed ───────────────────────────────────────────────────

INSUFFICIENT_BALANCE = 'INSUFFICIENT_BALANCE'
WRONG_PIN = 'WRONG_PIN'
USER_CANCELLED = 'USER_CANCELLED'
REJECTED = 'REJECTED'
TIMEOUT = 'TIMEOUT'
UNKNOWN = 'UNKNOWN'

#: What the customer is told. Written for somebody who has just had a payment
#: fail and wants to know whether they were charged and what to do next.
REASON_MESSAGES = {
    INSUFFICIENT_BALANCE: (
        'Your telebirr balance was not enough to complete this payment. '
        'Top up and try again -- you have not been charged.'
    ),
    WRONG_PIN: (
        'The PIN entered was not correct, so the payment was not completed. '
        'You have not been charged.'
    ),
    USER_CANCELLED: 'The payment was cancelled, so nothing was charged.',
    REJECTED: (
        'telebirr could not complete this payment. '
        'Please try again, or contact telebirr if it keeps happening.'
    ),
    TIMEOUT: (
        'The payment request expired before it was approved. '
        'Nothing was charged -- please try again.'
    ),
    UNKNOWN: 'The payment was not completed. You have not been charged.',
}


def reason_message(reason: str | None) -> str:
    return REASON_MESSAGES.get(reason or UNKNOWN, REASON_MESSAGES[UNKNOWN])


# Matched against the provider's own wording. Ordered: the first pattern that
# matches wins, so the specific ones come before the general ones.
#
# These are read from ResultDesc, which is free text the provider may reword.
# A miss costs a specific message, never a wrong state -- an unrecognised
# description is still a failure, just described generically.
_REASON_PATTERNS: tuple[tuple[str, str], ...] = (
    (INSUFFICIENT_BALANCE, r'insufficient|not\s+enough|low\s+balance|balance\s+is\s+not'),
    (WRONG_PIN, r'\bpin\b|password|credential'),
    (USER_CANCELLED, r'cancel|abort|dismiss|user\s+decline'),
    (TIMEOUT, r'time[\s-]?out|timed\s+out|expire'),
    (REJECTED, r'reject|decline|refus|denied|not\s+permitted|forbidden'),
)


def classify_reason(description: str | None) -> str:
    """The reason behind a non-success result, from the provider's wording."""
    text = (description or '').lower()
    if not text.strip():
        return UNKNOWN
    for reason, pattern in _REASON_PATTERNS:
        if re.search(pattern, text):
            return reason
    return UNKNOWN


# ── USSD Push (BuyGoodsForCustomer) ──────────────────────────────────────────


def from_ussd_result(result_code, result_type, description=None) -> tuple[str, str | None]:
    """The state of a USSD Push payment from its Result callback.

    ``ResultCode 0`` with ``ResultType 0`` is the only success telebirr
    defines; every other combination is a payment that did not happen. The
    reason is read from the description, and a cancellation is reported as its
    own state because "you cancelled it" and "it failed" are different things
    to be told.

    Returns ``(state, reason)``; reason is None for a success.
    """
    code = '' if result_code is None else str(result_code).strip()
    rtype = '' if result_type is None else str(result_type).strip()

    if code == '0' and rtype == '0':
        return SUCCESS, None

    reason = classify_reason(description)
    if reason == USER_CANCELLED:
        return CANCELLED, reason
    return FAILED, reason


# ── H5 / SuperApp checkout (payment.queryorder) ──────────────────────────────

#: order_status values from the checkout API. Anything not listed is treated
#: as still in flight, because inventing a terminal state for a status this
#: code has never seen is how a pending payment comes to be shown as failed.
_H5_ORDER_STATES = {
    'PAY_SUCCESS': (SUCCESS, None),
    'SUCCESS': (SUCCESS, None),
    'COMPLETED': (SUCCESS, None),
    'PAY_FAILED': (FAILED, REJECTED),
    'FAILED': (FAILED, REJECTED),
    'CLOSED': (CANCELLED, USER_CANCELLED),
    'CANCELLED': (CANCELLED, USER_CANCELLED),
    'CANCELED': (CANCELLED, USER_CANCELLED),
    'PAY_TIMEOUT': (FAILED, TIMEOUT),
    'TIMEOUT': (FAILED, TIMEOUT),
    'WAIT_PAY': (PENDING, None),
    'PAYING': (PENDING, None),
    'PENDING': (PENDING, None),
    'INIT': (PENDING, None),
}

#: trade_status, which the async notify carries instead of order_status.
_H5_TRADE_STATES = {
    'COMPLETED': (SUCCESS, None),
    'SUCCESS': (SUCCESS, None),
    'PAY_SUCCESS': (SUCCESS, None),
    'FAILED': (FAILED, REJECTED),
    'CLOSED': (CANCELLED, USER_CANCELLED),
    'CANCELLED': (CANCELLED, USER_CANCELLED),
    'TIMEOUT': (FAILED, TIMEOUT),
    'WAITING': (PENDING, None),
    'WAIT_PAY': (PENDING, None),
    'PENDING': (PENDING, None),
}


def from_h5_order(order_status=None, trade_status=None, description=None) -> tuple[str, str | None]:
    """The state of an H5 / SuperApp checkout order.

    ``order_status`` is what queryOrder answers with and is preferred;
    ``trade_status`` is what the async notify carries. An order neither
    recognises is PENDING, never FAILED: the customer is told it is still
    being confirmed, which is true, instead of being told it failed when it
    may yet succeed.
    """
    order = (order_status or '').strip().upper()
    if order in _H5_ORDER_STATES:
        state, reason = _H5_ORDER_STATES[order]
    else:
        trade = (trade_status or '').strip().upper()
        if trade in _H5_TRADE_STATES:
            state, reason = _H5_TRADE_STATES[trade]
        else:
            return PENDING, None

    if state in (FAILED, CANCELLED) and description:
        # The provider's own wording is more specific than the status name
        # when it says anything useful.
        from_text = classify_reason(description)
        if from_text != UNKNOWN:
            reason = from_text
            if from_text == USER_CANCELLED:
                state = CANCELLED
    return state, reason


# ── what the client is handed ────────────────────────────────────────────────


def payload(state: str, reason: str | None = None, **extra) -> dict:
    """The shape every payment-status response shares.

    ``state`` is what a client switches on. ``message`` is there so no client
    has to write its own copy for a failure and get it subtly wrong, and
    ``is_final`` spares each of them from keeping its own list of which states
    stop a poll.
    """
    body = {
        'state': state,
        'is_final': is_terminal(state),
        'reason': reason,
    }
    if state != SUCCESS:
        body['message'] = reason_message(reason)
    body.update(extra)
    return body
