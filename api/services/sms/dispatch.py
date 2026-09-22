"""
Queueing an SMS, and delivering it.

The public entry point for the whole application is :func:`queue_sms`. It
writes a row and returns; it never touches the network. Everything that can
block -- binding, reconnecting, waiting on a gateway -- happens later in the
SMS worker, so no HTTP request ever waits on SMPP.

Idempotency
-----------
Every message carries a key its caller chooses, and the key is unique. Sending
"the welcome SMS for subscription X" twice finds the existing row instead of
creating a second one, which is what stops a Celery retry, a duplicated task
or a worker restart producing two OTPs -- where the second silently
invalidates the first.

The ambiguous case
------------------
A network failure *after* ``submit_sm`` is not the same as one before it. The
gateway may hold the message already. Resending would put two OTPs on one
handset; not resending may lose the message. Neither is safely automatic, so
:class:`SmppSubmitUncertain` parks the row in FAILED with the reason recorded
and does **not** retry. That is a deliberate bias: a subscriber who receives
nothing contacts support, while one who receives two codes cannot log in with
either.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from api.integrations.smpp.errors import (
    SmppConnectionError,
    SmppNotConfigured,
    SmppSubmitRejected,
    SmppSubmitUncertain,
)
from api.models.sms import SmsMessage, SmsStatus
from api.services.sms import get_gateway
from common.validators.phone import normalize_ethiopian_phone

logger = logging.getLogger(__name__)


class SmsNotQueued(Exception):
    """The message could not even be recorded -- e.g. an unusable number."""


def queue_sms(*, phone_number, text, purpose='', idempotency_key=None, provider=''):
    """Record an SMS and hand it to the worker. Returns the SmsMessage.

    Never raises for gateway problems, because none are consulted here. A
    caller that gets a row back knows the message is durable, not that it has
    been delivered -- those are different questions and
    ``SmsMessage.status`` answers the second.
    """
    # One normalisation for the whole system: the same 251XXXXXXXXX form used
    # for storage and lookups is what the SMPP destination gets, so a number
    # that works for login works for SMS.
    destination = normalize_ethiopian_phone(phone_number)
    if not destination:
        raise SmsNotQueued(f'Not a usable Ethiopian number: {phone_number!r}')
    if not text:
        raise SmsNotQueued('Refusing to queue an empty message.')

    key = idempotency_key or f'{purpose or "sms"}:{destination}:{timezone.now().timestamp()}'

    try:
        with transaction.atomic():
            message = SmsMessage.objects.create(
                idempotency_key=key,
                recipient=destination,
                body=text,
                purpose=purpose,
                # Which transport this message wants. Blank means the
                # configured MA/SMPP default; Telebirr activation notices pin
                # the same provider explicitly.
                provider=provider,
                status=SmsStatus.QUEUED,
            )
    except IntegrityError:
        # Someone already queued this exact message. Returning theirs is the
        # whole point of the key.
        existing = SmsMessage.objects.get(idempotency_key=key)
        logger.info(
            'SMS_DUPLICATE_SUPPRESSED sms_id=%s purpose=%s to=%s',
            existing.id,
            existing.purpose,
            existing.masked_recipient,
        )
        return existing

    logger.info(
        'SMS_QUEUED sms_id=%s purpose=%s to=%s len=%s',
        message.id,
        purpose,
        message.masked_recipient,
        len(text),
    )

    # Enqueued after commit so the worker cannot read a row that is not there
    # yet -- the classic race when a task is dispatched inside a transaction.
    def _enqueue():
        from api.tasks.sms import deliver_sms

        deliver_sms.delay(str(message.id))

    transaction.on_commit(_enqueue)
    return message


def deliver(message_id):
    """Submit one queued message. Called by the worker, not by requests.

    Returns the refreshed SmsMessage. Raises only for conditions a Celery
    retry could plausibly fix -- see the module docstring for why the
    ambiguous case is not one of them.
    """
    message = SmsMessage.objects.filter(pk=message_id).first()
    if message is None:
        logger.warning('SMS_SUBMIT_FAILED sms_id=%s reason=no_such_message', message_id)
        return None

    if message.is_terminal:
        # Already resolved. A duplicate task delivery must not re-send.
        logger.info('SMS_ALREADY_FINAL sms_id=%s status=%s', message.id, message.status)
        return message

    if message.submitted_at is not None:
        # We have been here before and the gateway saw it. Re-submitting now
        # would duplicate a message that may already have arrived.
        logger.warning(
            'SMS_RESUBMIT_SUPPRESSED sms_id=%s status=%s submitted_at=%s',
            message.id,
            message.status,
            message.submitted_at,
        )
        return message

    # The message's own transport when it asked for one, the configured
    # default otherwise. Called with no argument in the default case so the
    # signature every existing caller and test stub relies on is unchanged --
    # only a message that pinned a provider takes the other branch.
    gateway = get_gateway(message.provider) if message.provider else get_gateway()
    SmsMessage.objects.filter(pk=message.pk).update(attempts=message.attempts + 1)

    logger.info(
        'SMS_SUBMIT_STARTED sms_id=%s provider=%s to=%s',
        message.id,
        gateway.name,
        message.masked_recipient,
    )

    try:
        result = gateway.submit(destination=message.recipient, text=message.body)
    except SmppNotConfigured as exc:
        _fail(message, gateway.name, 'not_configured', str(exc))
        # Not retryable: no amount of waiting configures a gateway.
        return message
    except SmppSubmitRejected as exc:
        _fail(message, gateway.name, exc.code_label, str(exc))
        SmsMessage.objects.filter(pk=message.pk).update(status=SmsStatus.REJECTED)
        return message
    except SmppSubmitUncertain as exc:
        # The dangerous one. Recorded as failed AND marked submitted, so no
        # later attempt re-sends it.
        SmsMessage.objects.filter(pk=message.pk).update(
            status=SmsStatus.FAILED,
            provider=gateway.name,
            submitted_at=timezone.now(),
            error_code='uncertain',
            error_message=str(exc)[:2000],
        )
        logger.error(
            'SMS_SUBMIT_UNCERTAIN sms_id=%s provider=%s to=%s -- not retrying, '
            'the gateway may already hold this message',
            message.id,
            gateway.name,
            message.masked_recipient,
        )
        return message.__class__.objects.get(pk=message.pk)
    except SmppConnectionError as exc:
        # Nothing was accepted, so a retry is safe and wanted.
        _fail(message, gateway.name, 'connection', str(exc))
        raise

    SmsMessage.objects.filter(pk=message.pk).update(
        status=SmsStatus.SUBMITTED,
        provider=result.provider,
        provider_message_id=result.message_id or '',
        submitted_at=timezone.now(),
        error_code='',
        error_message='',
    )
    logger.info(
        'SMS_SENT sms_id=%s provider=%s message_id=%s to=%s',
        message.id,
        result.provider,
        result.message_id,
        message.masked_recipient,
    )
    return SmsMessage.objects.get(pk=message.pk)


def _fail(message, provider, code, detail):
    SmsMessage.objects.filter(pk=message.pk).update(
        status=SmsStatus.FAILED,
        provider=provider,
        error_code=code[:64],
        error_message=str(detail)[:2000],
    )
    logger.warning(
        'SMS_SUBMIT_FAILED sms_id=%s provider=%s code=%s to=%s detail=%s',
        message.id,
        provider,
        code,
        message.masked_recipient,
        # Truncated: exception messages can be long, and should never carry
        # credentials, but a safe sanity cap keeps log lines short.
        str(detail)[:200],
    )


def record_delivery_receipt(receipt):
    """Apply a delivery receipt to the message it names.

    A receipt for an unknown id is logged and dropped: it belongs to another
    system sharing the bind, or to a message older than our records.
    """
    if not receipt.message_id:
        logger.warning('SMS_DLR_UNPARSED raw=%s', receipt.raw[:200])
        return None

    message = SmsMessage.objects.filter(provider_message_id=receipt.message_id).first()
    if message is None:
        logger.warning('SMS_DLR_UNMATCHED message_id=%s stat=%s', receipt.message_id, receipt.stat)
        return None

    status = receipt.status
    if status is None:
        # The gateway said something we do not have a mapping for. Recorded
        # verbatim rather than guessed at.
        SmsMessage.objects.filter(pk=message.pk).update(raw_dlr=receipt.raw[:2000])
        logger.warning('SMS_DLR_UNKNOWN_STAT sms_id=%s stat=%s', message.id, receipt.stat)
        return message

    updates = {
        'status': status,
        'raw_dlr': receipt.raw[:2000],
        'error_code': receipt.error_code[:64] if receipt.error_code else '',
    }
    if status == SmsStatus.DELIVERED:
        updates['delivered_at'] = timezone.now()

    SmsMessage.objects.filter(pk=message.pk).update(**updates)

    event = 'SMS_DELIVERED' if status == SmsStatus.DELIVERED else 'SMS_DELIVERY_FAILED'
    logger.info(
        '%s sms_id=%s message_id=%s stat=%s to=%s',
        event,
        message.id,
        receipt.message_id,
        receipt.stat,
        message.masked_recipient,
    )
    return SmsMessage.objects.get(pk=message.pk)
