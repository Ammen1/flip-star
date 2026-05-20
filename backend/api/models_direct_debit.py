"""
Telebirr Direct Debit Mandate Models

Stores direct debit mandates for recurring subscription payments.
Integrates with Telebirr SOAP API for mandate lifecycle management.
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class DirectDebitMandate(models.Model):
    """
    Direct Debit Mandate for recurring payments via Telebirr.
    
    Lifecycle:
    1. pending_created - Mandate creation requested, awaiting Telebirr response
    2. pending_active - Mandate created, awaiting user activation
    3. active - Mandate active, can be used for debits
    4. cancelled - Mandate cancelled by payer
    5. expired - Mandate expired
    6. failed - Mandate creation/activation failed
    """
    
    STATUS_CHOICES = [
        ('pending_created', 'Pending Creation'),
        ('pending_active', 'Pending Activation'),
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('failed', 'Failed'),
    ]

    PAYMENT_TYPE_CHOICES = [
        ('recurring', 'Recurring Subscription'),
        ('one_off', 'One-Off Payment'),
    ]
    
    IDENTIFIER_TYPE_CHOICES = [
        (1, 'MSISDN'),
        (4, 'Shortcode'),
        (11, 'Organization Operator ID'),
        (14, 'SP Operator Username'),
        (53, 'Payer Reference Number'),
    ]
    
    FREQUENCY_CHOICES = [
        ('01', 'Once'),
        ('02', 'Daily'),
        ('03', 'Weekly'),
        ('04', 'Bi-weekly'),
        ('05', 'Monthly'),
        ('06', 'Quarterly'),
        ('07', 'Half-yearly'),
        ('08', 'Yearly'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Payer (customer who authorizes the debit)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='direct_debit_mandates')
    payer_msisdn = models.CharField(max_length=20, help_text='Payer phone number (MSISDN)')
    payer_reference_number = models.CharField(max_length=100, help_text='Payer reference number for mandate')
    payer_account_name = models.CharField(max_length=64, blank=True, help_text='Payer account name')
    
    # Payee (Flipstar as merchant)
    payee_identifier_type = models.IntegerField(choices=IDENTIFIER_TYPE_CHOICES, default=4, help_text='Payee identifier type')
    payee_identifier_value = models.CharField(max_length=50, help_text='Payee shortcode or ID')
    payee_account_name = models.CharField(max_length=64, default='Flipstar', help_text='Payee account name')
    
    # Mandate details
    mandate_id = models.CharField(max_length=18, blank=True, null=True, help_text='Telebirr mandate ID (max 18 bytes)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_created')
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, default='recurring', help_text='Payment type: recurring or one-off')
    
    # Mandate configuration
    frequency = models.CharField(max_length=2, choices=FREQUENCY_CHOICES, help_text='Debit frequency')
    first_payment_date = models.DateField(help_text='First payment date')
    expiry_date = models.DateField(help_text='Mandate expiry date')
    start_range_of_days = models.IntegerField(default=1, help_text='Start range of days for payment')
    end_range_of_days = models.IntegerField(default=22, help_text='End range of days for payment')
    agreed_tc = models.BooleanField(default=False, help_text='User agreed to terms and conditions')
    
    # Telebirr tracking
    originator_conversation_id = models.CharField(max_length=100, blank=True, help_text='Originator conversation ID')
    conversation_id = models.CharField(max_length=100, blank=True, help_text='Telebirr conversation ID')
    
    # Subscription tier the mandate was created for (set at create time so
    # activation can build the SubscriptionPlan even before subscription_plan
    # is linked).
    tier = models.ForeignKey(
        'api.SubscriptionTier',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='direct_debit_mandates',
        help_text='Subscription tier this mandate was created for'
    )

    # Linked subscription
    subscription_plan = models.ForeignKey(
        'api.SubscriptionPlan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='direct_debit_mandates',
        help_text='Linked subscription plan'
    )
    
    # Additional data
    metadata = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, help_text='Error message if mandate failed')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['mandate_id']),
            models.Index(fields=['payer_msisdn']),
        ]
        verbose_name = 'Direct Debit Mandate'
        verbose_name_plural = 'Direct Debit Mandates'
    
    def __str__(self):
        return f"{self.user.username} - {self.mandate_id or 'Pending'} ({self.status})"
    
    def activate(self):
        """Activate the mandate"""
        self.status = 'active'
        self.activated_at = timezone.now()
        self.save()
    
    def cancel(self):
        """Cancel the mandate"""
        self.status = 'cancelled'
        self.cancelled_at = timezone.now()
        self.save()
    
    def mark_expired(self):
        """Mark mandate as expired"""
        self.status = 'expired'
        self.save()
    
    def mark_failed(self, error_message=''):
        """Mark mandate as failed"""
        self.status = 'failed'
        self.error_message = error_message
        self.save()
    
    def is_active(self):
        """Check if mandate is active and not expired"""
        return (
            self.status == 'active' and
            self.expiry_date and
            self.expiry_date >= timezone.now().date()
        )


class DirectDebitTransaction(models.Model):
    """
    Direct debit transaction records.
    Tracks each debit attempt using a mandate.
    """
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('timeout', 'Timeout'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Reference to mandate
    mandate = models.ForeignKey(
        DirectDebitMandate,
        on_delete=models.CASCADE,
        related_name='transactions',
        help_text='Associated mandate'
    )
    
    # Transaction details
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text='Debit amount')
    currency = models.CharField(max_length=3, default='ETB', help_text='Currency code')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Telebirr response
    telebirr_transaction_id = models.CharField(max_length=100, blank=True, help_text='Telebirr transaction ID')
    originator_conversation_id = models.CharField(max_length=100, blank=True, help_text='Originator conversation ID')
    conversation_id = models.CharField(max_length=100, blank=True, help_text='Telebirr conversation ID')
    
    # Linked subscription payment
    subscription_payment = models.ForeignKey(
        'api.SubscriptionPayment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='direct_debit_transactions',
        help_text='Associated subscription payment'
    )
    
    # Error handling
    error_message = models.TextField(blank=True, help_text='Error message if transaction failed')
    retry_count = models.IntegerField(default=0, help_text='Number of retry attempts')
    
    # Additional data
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['mandate', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['telebirr_transaction_id']),
        ]
        verbose_name = 'Direct Debit Transaction'
        verbose_name_plural = 'Direct Debit Transactions'
    
    def __str__(self):
        return f"{self.mandate.user.username} - {self.amount} {self.currency} ({self.status})"
    
    def mark_success(self, telebirr_transaction_id=''):
        """Mark transaction as successful"""
        self.status = 'success'
        self.completed_at = timezone.now()
        if telebirr_transaction_id:
            self.telebirr_transaction_id = telebirr_transaction_id
        self.save()
    
    def mark_failed(self, error_message=''):
        """Mark transaction as failed"""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.retry_count += 1
        self.save()
