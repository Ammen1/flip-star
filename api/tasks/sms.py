"""
Delivering SMS off the request path.

Why a task at all
-----------------
SMPP is a persistent TCP session. Binding, reconnecting and waiting on a
gateway are all things that can take seconds, and none of them belong in an
HTTP request -- a subscriber's payment callback must not hang because a
telecom link is flapping. The request writes a row and returns; this task
does the network part.

Why its own queue
-----------------
Routed to ``sms`` by ``CELERY_TASK_ROUTES``, consumed only by the
single-replica ``--pool=solo`` SMS worker. The general workers run two
replicas at concurrency four -- eight processes, and so eight SMPP binds if
they ever picked this up. One process owns the session; the queue is what
enforces it.

Retries
-------
Only for failures that certainly sent nothing. A connection error before
``submit_sm`` is safe to repeat; an unacknowledged submission is not, and
``dispatch.deliver`` swallows that case deliberately rather than raising it
here. See its module docstring.
"""

import logging

from celery import shared_task

from api.integrations.smpp.errors import SmppConnectionError

logger = logging.getLogger(__name__)

#: Backoff for a link that is down. Capped so a long outage does not park a
#: subscriber's OTP for an hour -- past this it is a failure worth seeing.
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 10


@shared_task(
    bind=True,
    name='api.tasks.sms.deliver_sms',
    max_retries=MAX_RETRIES,
    acks_late=True,
    # If the worker dies mid-task the message goes back on the queue. That is
    # safe here only because deliver() refuses to re-submit anything already
    # carrying submitted_at.
    reject_on_worker_lost=True,
)
def deliver_sms(self, sms_id, tier_type=None):
    """Submit one queued SmsMessage."""
    from api.services.sms import dispatch

    try:
        message = dispatch.deliver(sms_id, tier_type=tier_type)
    except SmppConnectionError as exc:
        # Nothing reached the gateway, so repeating is safe.
        countdown = RETRY_BACKOFF_SECONDS * (2**self.request.retries)
        logger.warning(
            'SMS_RETRY sms_id=%s attempt=%s/%s countdown=%ss reason=%s',
            sms_id,
            self.request.retries + 1,
            MAX_RETRIES,
            countdown,
            type(exc).__name__,
        )
        raise self.retry(exc=exc, countdown=countdown) from exc

    return str(message.status) if message is not None else 'missing'
