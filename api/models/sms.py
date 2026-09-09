"""
Outbound SMS and its delivery state.

Why a model rather than fire-and-forget
---------------------------------------
SMPP is asynchronous in both directions. ``submit_sm`` returns a gateway
message id, and the delivery receipt for that id arrives later on the same
bind -- possibly minutes later, possibly never. Without somewhere to write the
id down there is nothing to correlate the receipt against, and no way to
answer "did the subscriber actually get their OTP".

It also gives retries something to be idempotent against. A network timeout
after ``submit_sm`` is ambiguous: the gateway may have accepted the message or
may not have seen it. Re-sending blindly means a subscriber receives two OTPs
and the second invalidates the first. The row, keyed by an idempotency key the
caller controls, is what makes the answer knowable.

Deliberately separate from subscription and payment models. SMS delivery is
not payment state: a subscription is valid whether or not its welcome message
arrived, and a failed SMS must never roll back a charge that succeeded.
"""

import uuid

from django.db import models


class SmsStatus(models.TextChoices):
    """Where a message has actually got to.

    The distinction that matters is SUBMITTED vs DELIVERED. ``submit_sm``
    succeeding means the gateway accepted the message, not that a handset
    received it -- only a delivery receipt can say that. Treating acceptance
    as delivery is how "we sent it" turns into a support ticket.
    """

    QUEUED = 'queued', 'Queued'
    SUBMITTED = 'submitted', 'Submitted to gateway'
    DELIVERED = 'delivered', 'Delivered to handset'
    FAILED = 'failed', 'Failed'
    REJECTED = 'rejected', 'Rejected by gateway'
    EXPIRED = 'expired', 'Expired before delivery'


#: States from which no further transition happens.
TERMINAL_STATUSES = (
    SmsStatus.DELIVERED,
    SmsStatus.FAILED,
    SmsStatus.REJECTED,
    SmsStatus.EXPIRED,
)


class SmsMessage(models.Model):
    """One outbound SMS, from queueing to final delivery state."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    #: The caller's own name for this message. Two attempts to send "the
    #: welcome SMS for subscription X" share a key and so share a row, which
    #: is what stops a Celery retry or a worker restart producing a second
    #: OTP. Unique, and required -- a caller that cannot name its message
    #: cannot be made idempotent.
    idempotency_key = models.CharField(max_length=255, unique=True)

    #: Normalised to 251XXXXXXXXX by common.validators.phone before it gets
    #: here, so lookups and the SMPP destination agree.
    recipient = models.CharField(max_length=20, db_index=True)
    body = models.TextField()

    #: What this message is for -- 'subscription_welcome', 'login_otp'. Used
    #: for metrics and for finding the messages behind a support question.
    purpose = models.CharField(max_length=64, blank=True, default='')

    status = models.CharField(
        max_length=20, choices=SmsStatus.choices, default=SmsStatus.QUEUED, db_index=True
    )
    provider = models.CharField(max_length=32, blank=True, default='')

    #: The gateway's own id, returned by submit_sm. The delivery receipt
    #: quotes it, and it is the only way to match one to the other.
    provider_message_id = models.CharField(max_length=128, blank=True, default='', db_index=True)

    #: Non-null once submit_sm has been attempted at all. Its presence is what
    #: makes a retry ask "did this already go?" rather than just re-sending.
    submitted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    attempts = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True, default='')
    error_message = models.TextField(blank=True, default='')

    #: The delivery receipt as received, for diagnosing a gateway dispute.
    #: Receipts carry a message id and a status, not credentials.
    raw_dlr = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f'{self.purpose or "sms"} to {self.masked_recipient} [{self.status}]'

    @property
    def masked_recipient(self) -> str:
        """The number with its middle digits hidden, for logs and admin.

        A full MSISDN in a log line is subscriber PII that outlives the reason
        it was written; the last few digits are enough to recognise a number
        you already have.
        """
        number = self.recipient or ''
        if len(number) <= 6:
            return number
        return f'{number[:5]}****{number[-3:]}'

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES
