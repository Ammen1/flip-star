"""
Telling a subscriber what happened to their withdrawal.

A withdrawal is the one place where a user hands over something of theirs --
points -- and then waits for money to appear somewhere else: a telebirr
wallet, a bank account. Until now none of it was reported. Not the payout,
not a failure, not the refund that follows one. The only way to find out was
to open the app and look, or to notice the money arriving.

Two messages, and only two, because each one costs money to send:

* **paid** -- the money has left. This is the receipt, with the reference the
  user needs if they have to ask their bank or telebirr about it.
* **failed** -- it did not, and here is what happened to their points.

Whether the points came back is passed in by the caller rather than guessed
from the status: the automatic payout paths refund them, and admin rejection
currently does not (see WithdrawalRequest.mark_rejected). Telling somebody
their points are back when they are not would be worse than saying nothing.

Never raises. A withdrawal that has been paid must not be un-paid, nor a
webhook answered with an error, because a text message could not be queued.
"""

import logging

logger = logging.getLogger(__name__)

#: How each payout method reads in the message.
METHOD_LABELS = {
    'telebirr': 'telebirr',
    'bank_transfer': 'bank',
    'cbe_birr': 'CBE Birr',
    'mpesa': 'M-Pesa',
}

#: Methods whose "account" is a mobile number, and so can be texted when the
#: account holder has no number on their profile.
PHONE_METHODS = frozenset({'telebirr', 'mpesa', 'cbe_birr'})


def _mask(account):
    """`251911528271` -> `25191****271`. Enough for the user to recognise
    which account they used, not enough to be worth intercepting."""
    text = str(account or '').strip()
    return f'{text[:5]}****{text[-3:]}' if len(text) > 8 else text


def _recipient(withdrawal):
    """The number to text: the account holder's own, else the payout account
    when that is itself a phone number."""
    profile = getattr(getattr(withdrawal, 'user', None), 'profile', None)
    registered = (getattr(profile, 'phone_number', '') or '').strip()
    if registered:
        return registered
    if withdrawal.payout_method in PHONE_METHODS:
        return (withdrawal.payout_account or '').strip()
    return ''


def _amount(value):
    """`120.00` -> `120`, `120.50` -> `120.50`. Money reads better without the
    decimals that are not there."""
    number = float(value or 0)
    return str(int(number)) if number == int(number) else f'{number:.2f}'


def build_paid_message(withdrawal):
    method = METHOD_LABELS.get(withdrawal.payout_method, withdrawal.payout_method or 'account')
    account = _mask(withdrawal.payout_account)
    where = f' to your {method} account {account}' if account else f' to your {method} account'
    reference = (withdrawal.payout_reference or '').strip()
    ref = f' Reference: {reference}.' if reference else ''
    return (
        f'Dear valued customer, your Flipstar withdrawal of '
        f'{_amount(withdrawal.net_birr)} ETB has been sent{where}.{ref} '
        f'Thank you for using Flipstar.'
    )


def build_failed_message(withdrawal, *, refunded):
    points = withdrawal.point_amount or withdrawal.coin_amount or 0
    outcome = (
        f' Your {points} points have been returned to your balance.'
        if refunded
        else ' Please contact Flipstar support.'
    )
    return (
        f'Dear valued customer, your Flipstar withdrawal of '
        f'{_amount(withdrawal.net_birr)} ETB could not be completed.{outcome}'
    )


def _send(withdrawal, message, *, purpose, event):
    """Queue one message about this withdrawal, at most once per event.

    The idempotency key is the withdrawal and the event, so a Telebirr webhook
    that arrives twice -- which it does -- cannot text the user twice.
    """
    number = _recipient(withdrawal)
    if not number:
        logger.warning(
            'WITHDRAWAL_SMS_NO_NUMBER withdrawal=%s user=%s',
            withdrawal.id,
            withdrawal.user_id,
        )
        return False

    from api.services.sms.dispatch import queue_sms

    try:
        queue_sms(
            phone_number=number,
            text=message,
            purpose=purpose,
            idempotency_key=f'withdrawal:{withdrawal.id}:{event}',
        )
    except Exception:
        # Including SmsNotQueued: an unusable number, or a gateway that is not
        # configured. The payout stands either way.
        logger.exception('WITHDRAWAL_SMS_NOT_QUEUED withdrawal=%s event=%s', withdrawal.id, event)
        return False
    logger.info('WITHDRAWAL_SMS_QUEUED withdrawal=%s event=%s', withdrawal.id, event)
    return True


def notify_paid(withdrawal):
    """The money has been sent. Safe to call twice; the second is suppressed."""
    return _send(
        withdrawal,
        build_paid_message(withdrawal),
        purpose='withdrawal_paid',
        event='paid',
    )


def notify_failed(withdrawal, *, refunded):
    """The payout did not happen. ``refunded`` says whether the points are
    already back, because the message says so and must be true."""
    return _send(
        withdrawal,
        build_failed_message(withdrawal, refunded=refunded),
        purpose='withdrawal_failed',
        event='failed',
    )
