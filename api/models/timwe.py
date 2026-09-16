"""
TIMWE Master Aggregator integration records.

Two audit tables, one per direction of the integration:

``TimweSyncOrderLog``
    Every inbound syncOrderRelation the MA sends us. Written before the
    subscription change is applied and updated afterwards, so a request that
    crashes mid-apply still leaves a record of what arrived.

``TimweChargeTransaction``
    Every outbound chargeAmount, keyed by the ``referenceCode`` we generate.
    This is the billing ledger: it must survive even when the MA never
    answers, because "we do not know whether the subscriber was charged" is a
    state that needs resolving by hand.

These replace ``OnevasWebhookLog`` and ``OnevasChargingTransaction``, which
now only hold OneVAS's history -- see docs/integrations.md.
"""

import uuid

from django.contrib.auth.models import User
from django.db import models


class TimweSyncOrderLog(models.Model):
    """One inbound syncOrderRelation request from the MA."""

    EVENT_TYPES = [
        ('subscription', 'Subscription'),
        ('unsubscription', 'Unsubscription'),
        ('update', 'Update'),
        ('unknown', 'Unknown'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, default='unknown')
    update_type = models.IntegerField(null=True, blank=True, help_text='1 Add, 2 Delete, 3 Update')

    msisdn = models.CharField(max_length=30, blank=True, db_index=True)
    sp_id = models.CharField(max_length=21, blank=True)
    product_id = models.CharField(max_length=21, blank=True, db_index=True)
    service_id = models.CharField(max_length=21, blank=True)

    #: The MA's own identifiers, carried in extensionInfo. transaction_id is
    #: what TIMWE support will quote when a subscriber disputes something. The
    #: MA's format is a long UUID-like token (observed 81 chars), far past the
    #: original 64, so it is kept roomy to avoid truncation errors on insert.
    transaction_id = models.CharField(max_length=128, blank=True, db_index=True)
    order_key = models.CharField(max_length=128, blank=True)
    keyword = models.CharField(max_length=32, blank=True)
    update_reason = models.CharField(max_length=16, blank=True)

    update_time = models.DateTimeField(null=True, blank=True)
    expiry_time = models.DateTimeField(null=True, blank=True)

    raw_payload = models.TextField(help_text='Verbatim SOAP request as received')
    extensions = models.JSONField(default=dict, blank=True)

    applied = models.BooleanField(
        default=False, help_text='Whether the subscription change was applied locally'
    )
    result_code = models.CharField(
        max_length=8, blank=True, help_text='Code returned to the MA; 0 is success'
    )
    result_description = models.TextField(blank=True)
    error_message = models.TextField(blank=True)

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='timwe_sync_logs',
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'TIMWE Sync Order Log'
        verbose_name_plural = 'TIMWE Sync Order Logs'
        indexes = [
            models.Index(fields=['msisdn', '-created_at']),
            models.Index(fields=['event_type', '-created_at']),
        ]

    def __str__(self):
        return f'{self.event_type} {self.msisdn} {self.created_at:%Y-%m-%d %H:%M}'


class TimweChargeTransaction(models.Model):
    """One outbound chargeAmount call."""

    PURPOSE_COIN_PURCHASE = 'coin_purchase'
    PURPOSE_SUBSCRIPTION_RENEWAL = 'subscription_renewal'
    PURPOSE_MANUAL_CHECK = 'manual_check'
    PURPOSE_CHOICES = [
        (PURPOSE_COIN_PURCHASE, 'Coin purchase'),
        (PURPOSE_SUBSCRIPTION_RENEWAL, 'Subscription renewal'),
        (PURPOSE_MANUAL_CHECK, 'Manual check'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('timeout', 'Timeout'),
        ('unknown', 'Unknown'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='timwe_charge_transactions',
    )

    #: Unique per charge request and capped at 30 characters by the guide
    #: (p.21). Unique here so a retry cannot double-bill under the same
    #: reference.
    reference_code = models.CharField(max_length=30, unique=True, db_index=True)

    msisdn = models.CharField(max_length=30, db_index=True)
    amount = models.DecimalField(
        max_digits=6,
        decimal_places=0,
        help_text='Whole currency units; the MA rejects a decimal point',
    )
    currency = models.CharField(max_length=3)
    description = models.CharField(max_length=255, blank=True)
    charge_code = models.CharField(max_length=30, blank=True)

    subscription_tier = models.ForeignKey(
        'api.SubscriptionTier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='timwe_charge_transactions',
    )

    #: The caller's name for this purchase. Unique, so a double tap, a client
    #: retry or a duplicated request finds the existing charge instead of
    #: starting a second one -- the difference between a subscriber being
    #: billed once and twice. Nullable only so rows written before this field
    #: existed remain valid; every charge made through
    #: api/services/timwe_charging.py sets it.
    idempotency_key = models.CharField(max_length=255, unique=True, null=True, blank=True)

    coin_package = models.ForeignKey(
        'api.CoinPackage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='timwe_charge_transactions',
        help_text='What the charge paid for, when it was a coin purchase',
    )

    #: What the charge was for. Blank only on rows written before it existed.
    purpose = models.CharField(max_length=32, choices=PURPOSE_CHOICES, blank=True, default='')

    #: For a renewal: the plan being renewed, and the end of the period that
    #: ran out. Together they name one renewal period, and the constraint below
    #: allows exactly one live charge for it -- pending, successful or
    #: ambiguous -- the database's half of "an expired subscription is charged
    #: once, however many requests arrive". Failed attempts are outside it: TIMWE
    #: refused them, nothing was taken, and the period may be tried again.
    subscription = models.ForeignKey(
        'api.SubscriptionPlan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='timwe_renewal_charges',
    )
    renewal_period_end = models.DateTimeField(
        null=True, blank=True, help_text='The end_date the renewal charge was for'
    )

    #: What the charge was made under, as it stood at the time -- for
    #: reconciling with TIMWE after the configuration has moved on.
    short_code = models.CharField(max_length=10, blank=True)
    service_id = models.CharField(max_length=32, blank=True)
    product_id = models.CharField(max_length=50, blank=True)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')

    #: Finer than ``status``, which folds two very different failures into
    #: 'failed'. ``rejected`` means the MA answered with a Fault; ``unreachable``
    #: means nothing was ever sent. Both are definite non-charges, but they are
    #: diagnosed completely differently -- one is a TIMWE conversation, the
    #: other a network one.
    outcome = models.CharField(max_length=16, blank=True)

    error_code = models.CharField(
        max_length=16, blank=True, help_text='SVC/POL code returned by the MA'
    )
    error_message = models.TextField(blank=True)
    retryable = models.BooleanField(default=False)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    #: When whatever the charge paid for was delivered -- coins credited, for a
    #: coin purchase. Set in the same database transaction as the credit, and
    #: claimed with a conditional UPDATE, so a successful charge is fulfilled
    #: exactly once however many times fulfilment is attempted.
    fulfilled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'TIMWE Charge Transaction'
        verbose_name_plural = 'TIMWE Charge Transactions'
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['msisdn', '-created_at']),
            models.Index(fields=['purpose', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['subscription', 'renewal_period_end'],
                condition=models.Q(purpose='subscription_renewal') & ~models.Q(status='failed'),
                name='timwe_one_live_renewal_charge_per_period',
            ),
        ]

    def __str__(self):
        return f'{self.reference_code} {self.amount} {self.currency} ({self.status})'

    @property
    def masked_msisdn(self) -> str:
        """The number with its middle hidden, for logs and admin screens.

        The full MSISDN is stored because reconciling with TIMWE needs it --
        they key their records by subscriber. It just does not belong in a log
        line that outlives the reason it was written.
        """
        number = self.msisdn or ''
        if len(number) <= 6:
            return number
        return f'{number[:5]}****{number[-3:]}'

    @property
    def is_ambiguous(self) -> bool:
        """The subscriber may have been charged, but the MA never confirmed."""
        return self.status in ('timeout', 'unknown') or (
            self.status == 'pending' and self.completed_at is None
        )
