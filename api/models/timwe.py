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

These replace ``OnevasWebhookLog`` and ``OnevasChargingTransaction``. Both of
those remain in place until the MA integration is credentialed and cut over --
see docs/integrations.md.
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
    #: what TIMWE support will quote when a subscriber disputes something.
    transaction_id = models.CharField(max_length=64, blank=True, db_index=True)
    order_key = models.CharField(max_length=64, blank=True)
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

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    error_code = models.CharField(
        max_length=16, blank=True, help_text='SVC/POL code returned by the MA'
    )
    error_message = models.TextField(blank=True)
    retryable = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'TIMWE Charge Transaction'
        verbose_name_plural = 'TIMWE Charge Transactions'
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['msisdn', '-created_at']),
        ]

    def __str__(self):
        return f'{self.reference_code} {self.amount} {self.currency} ({self.status})'
