"""
Telling a telebirr subscriber their plan is active.

Two flows reach this: the USSD push and the SuperApp. Both end with a payment
confirmed and a plan activated, and until now neither said anything -- the
subscriber paid and found out by opening the app. The short-code and TIMWE
flows already notify over SMPP and are deliberately left alone.

Why a separate transport
------------------------
Telebirr notices go over SkyConnect's HTTP API; everything else -- OTPs, the
short code, TIMWE -- stays on SMPP. That is a per-message choice, not a
global one, so introducing this provider cannot move a message that was
working before. `queue_sms(provider=...)` is what carries it.

Why not a separate pipeline
---------------------------
None is needed. `queue_sms` already owns the parts that are easy to get
wrong: a unique key that makes a repeated webhook find the existing row
instead of sending twice, a durable record of what was sent and what happened
to it, retry for failures worth retrying, and masking so a number never
reaches a log in full. Adding a transport should not mean rebuilding any of
that.

Why nothing here raises
-----------------------
A subscription that has been paid for is not undone because a notification
failed. Every call site is inside or immediately after the transaction that
activates the plan, so an exception escaping would roll back an activation
the customer has already paid telebirr for -- or, on a webhook, return an
error that makes telebirr redeliver a payment that was in fact applied. The
failure is recorded on the SmsMessage row instead, where it can be found and
retried.
"""

import logging

logger = logging.getLogger(__name__)

#: The transport. Named here so a call site cannot pick a different one.
PROVIDER = 'skyconnect'

#: How the ledger is read back: "which telebirr subscribers did we notify?"
PURPOSE = 'telebirr_subscription_activated'

#: Where the subscription came from, recorded in the key so the two flows are
#: distinguishable in the ledger.
USSD = 'ussd'
SUPERAPP = 'superapp'


def build_activation_message(plan=None):
    """What the subscriber reads.

    Deliberately not `sms_subscription.build_welcome_message`: that one tells
    the reader to text STOP to a short code and quotes an OTP, because it is
    written for the short-code flow. Neither applies to a telebirr
    subscription, so reusing it would give accurate-sounding instructions that
    do not work. The voice is kept; the instructions are not.
    """
    tier = getattr(plan, 'tier', None)
    name = getattr(tier, 'name', '') or ''

    if name:
        message = (
            f'Dear valued customer, your Flipstar {name} subscription has been '
            f'activated successfully.'
        )
    else:
        message = 'Your Flipstar subscription has been activated successfully.'

    end_date = getattr(plan, 'end_date', None)
    if end_date:
        message += f' It is valid until {end_date.strftime("%Y-%m-%d")}.'
    return message


def _recipient(plan):
    """The subscriber's number.

    `telebirr_phone_number` first: it is the number that paid, which is the
    one the customer is holding. The profile number is the fallback for a
    plan that recorded the payer elsewhere.
    """
    number = getattr(plan, 'telebirr_phone_number', '') or ''
    if number:
        return number

    user = getattr(plan, 'user', None)
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'phone_number', '') or ''


def notify_activated(plan, *, source, payment=None):
    """Tell a telebirr subscriber their plan is live. Returns the SmsMessage.

    Returns None when there is nothing to send -- no plan, no number -- which
    is a fact about the data, not a failure. Never raises.

    The key is the payment when there is one, because a payment is exactly
    one activation: a webhook delivered three times produces one message. It
    falls back to the plan, which is still stable across redeliveries.
    """
    if plan is None:
        return None

    number = _recipient(plan)
    if not number:
        logger.warning(
            'TELEBIRR_SUB_SMS_NO_NUMBER plan=%s source=%s', getattr(plan, 'id', None), source
        )
        return None

    anchor = getattr(payment, 'pk', None) or getattr(plan, 'pk', None)
    key = f'telebirr-sub-active:{source}:{anchor}'

    try:
        from api.services.sms.dispatch import queue_sms

        message = queue_sms(
            phone_number=number,
            text=build_activation_message(plan),
            purpose=PURPOSE,
            idempotency_key=key,
            provider=PROVIDER,
        )
    except Exception:
        # Recorded, never raised: see the module docstring. A plan the
        # customer has paid for stays active whatever happens here.
        logger.exception(
            'TELEBIRR_SUB_SMS_FAILED plan=%s source=%s', getattr(plan, 'id', None), source
        )
        return None

    logger.info(
        'TELEBIRR_SUB_SMS_QUEUED plan=%s source=%s sms=%s',
        getattr(plan, 'id', None),
        source,
        message.id,
    )
    return message
