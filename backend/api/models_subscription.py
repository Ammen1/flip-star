from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
import uuid
import json


class SubscriptionTier(models.Model):
    """Subscription tiers with duration-based pricing"""
    
    DURATION_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('ondemand', 'OnDemand'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    
    # Duration and pricing
    duration_type = models.CharField(max_length=20, choices=DURATION_CHOICES)
    duration_days = models.IntegerField(null=True, blank=True, help_text='Null for OnDemand')
    price_etb = models.DecimalField(max_digits=10, decimal_places=2)
    price_coins = models.IntegerField(null=True, blank=True, help_text='Coin price (e.g., 100 coins)')
    
    # Onevas configuration
    onevas_code = models.CharField(max_length=10, unique=True, help_text='A, B, C, or D')
    spid = models.CharField(max_length=50, help_text='Service Provider ID')
    service_id = models.CharField(max_length=50, help_text='Onevas Service ID')
    product_id = models.CharField(max_length=50, help_text='Onevas Product ID')
    application_key = models.CharField(max_length=100, help_text='Onevas Application Key')
    short_code = models.CharField(max_length=10, default='9286')
    
    # Features and privileges
    features = models.JSONField(default=list, blank=True)
    privileges = models.JSONField(default=dict, blank=True)
    
    # Limits
    max_posts_per_day = models.IntegerField(default=0)
    max_reels_per_day = models.IntegerField(default=0)
    max_campaigns_per_month = models.IntegerField(default=0)
    max_likes_per_day = models.IntegerField(default=0)
    max_comments_per_day = models.IntegerField(default=0)
    max_follows_per_day = models.IntegerField(default=0)
    
    # Special features
    priority_support = models.BooleanField(default=False)
    custom_themes = models.BooleanField(default=False)
    analytics_access = models.BooleanField(default=False)
    api_access = models.BooleanField(default=False)
    ad_free = models.BooleanField(default=False)
    watermark_free = models.BooleanField(default=False)
    hd_quality = models.BooleanField(default=False)
    download_videos = models.BooleanField(default=False)
    
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['sort_order', 'price_etb']
        verbose_name = "Subscription Tier"
        verbose_name_plural = "Subscription Tiers"
    
    def __str__(self):
        return f"{self.name} - {self.price_etb} ETB"
    
    def clean(self):
        # Validate onevas code is uppercase
        if self.onevas_code:
            self.onevas_code = self.onevas_code.upper()
        
        # Validate ondemand has no duration
        if self.duration_type == 'ondemand' and self.duration_days:
            raise ValidationError("OnDemand tier should not have duration_days")
        
        # Validate other tiers have duration
        if self.duration_type != 'ondemand' and not self.duration_days:
            raise ValidationError(f"{self.duration_type} tier must have duration_days")
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class SubscriptionPlan(models.Model):
    """User subscriptions"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscription_plans', null=True, blank=True)
    tier = models.ForeignKey(SubscriptionTier, on_delete=models.SET_NULL, null=True, related_name='subscription_plans')
    
    # Onevas reference
    onevas_subscription_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    onevas_phone_number = models.CharField(max_length=20, null=True, blank=True)
    onevas_transaction_id = models.CharField(max_length=100, null=True, blank=True)
    subscription_source = models.CharField(max_length=20, choices=[('sms', 'SMS'), ('app', 'App')], default='app')
    setup_otp = models.CharField(max_length=6, null=True, blank=True, help_text='OTP for account setup after SMS subscription')
    
    # Status and dates
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    duration_type = models.CharField(max_length=20, choices=SubscriptionTier.DURATION_CHOICES)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    next_renewal_date = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    
    # Free trial tracking
    free_trial_days = models.IntegerField(default=0, help_text='Number of free trial days granted')
    
    # Cancellation
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    
    # Additional data
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['end_date']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.tier.name if self.tier else 'No Tier'} ({self.status})"
    
    @property
    def is_active(self):
        return self.status == 'active' and (self.end_date is None or self.end_date > timezone.now())
    
    def activate(self):
        """Activate subscription"""
        self.status = 'active'
        self.start_date = timezone.now()
        if self.tier and self.tier.duration_days:
            # Add free trial days to the duration
            total_days = self.tier.duration_days + self.free_trial_days
            self.end_date = timezone.now() + timezone.timedelta(days=total_days)
        self.save()
    
    def cancel(self, reason=''):
        """Cancel subscription"""
        self.status = 'cancelled'
        self.cancelled_at = timezone.now()
        self.cancellation_reason = reason
        self.auto_renew = False
        self.save()


class SubscriptionPayment(models.Model):
    """Subscription payment records"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('onevas', 'Onevas Airtime'),
        ('telebirr', 'Telebirr'),
        ('coins', 'Coins'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name='payments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscription_payments', null=True, blank=True)
    
    # Onevas reference
    onevas_transaction_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    
    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='ETB')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='onevas')
    
    # Period
    duration_type = models.CharField(max_length=20, choices=SubscriptionTier.DURATION_CHOICES)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    
    # Additional data
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.amount} {self.currency} ({self.status})"


class SubscriptionHistory(models.Model):
    """Subscription history tracking"""
    
    ACTION_CHOICES = [
        ('trial_started', 'Trial Started'),
        ('trial_ended', 'Trial Ended'),
        ('created', 'Subscription Created'),
        ('renewed', 'Subscription Renewed'),
        ('cancelled', 'Subscription Cancelled'),
        ('expired', 'Subscription Expired'),
        ('upgraded', 'Subscription Upgraded'),
        ('downgraded', 'Subscription Downgraded'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscription_history', null=True, blank=True)
    subscription = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='history')
    tier = models.ForeignKey(SubscriptionTier, on_delete=models.SET_NULL, null=True, blank=True, related_name='history')
    
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    previous_tier = models.ForeignKey(SubscriptionTier, on_delete=models.SET_NULL, null=True, blank=True, related_name='previous_history')
    new_tier = models.ForeignKey(SubscriptionTier, on_delete=models.SET_NULL, null=True, blank=True, related_name='new_history')
    reason = models.TextField(blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Subscription History"
        verbose_name_plural = "Subscription History"
    
    def __str__(self):
        return f"{self.user.username} - {self.action}"


class OnevasWebhookLog(models.Model):
    """Onevas webhook request logs"""
    
    WEBHOOK_TYPES = [
        ('subscription', 'Subscription'),
        ('unsubscription', 'Unsubscription'),
        ('renewal', 'Renewal'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    webhook_type = models.CharField(max_length=50, choices=WEBHOOK_TYPES)
    payload = models.JSONField()
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    processed = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Onevas Webhook Log"
        verbose_name_plural = "Onevas Webhook Logs"
    
    def __str__(self):
        return f"{self.webhook_type} - {self.created_at}"


class PromoCode(models.Model):
    """Promotional codes for subscriptions"""
    
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage'),
        ('fixed_amount', 'Fixed Amount'),
        ('free_trial', 'Free Trial'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    free_trial_days = models.IntegerField(null=True, blank=True)
    
    max_uses = models.IntegerField(null=True, blank=True)
    current_uses = models.IntegerField(default=0)
    
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    
    applicable_tiers = models.JSONField(default=list, blank=True)  # Array of tier IDs
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Promo Code"
        verbose_name_plural = "Promo Codes"
    
    def __str__(self):
        return f"{self.code} - {self.discount_type}"


class UserPromoUsage(models.Model):
    """Track promo code usage per user"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='promo_usage')
    promo_code = models.ForeignKey(PromoCode, on_delete=models.CASCADE, related_name='usages')
    subscription = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='promo_usages')
    used_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'promo_code']
        verbose_name = "User Promo Usage"
        verbose_name_plural = "User Promo Usages"
    
    def __str__(self):
        return f"{self.user.username} - {self.promo_code.code}"


class SubscriptionFeatureUsage(models.Model):
    """Track feature usage for subscribed users"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feature_usage')
    subscription = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='feature_usage')
    
    feature_name = models.CharField(max_length=100)
    usage_count = models.IntegerField(default=0)
    
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'feature_name', 'period_start']
        ordering = ['-period_start']
        verbose_name = "Subscription Feature Usage"
        verbose_name_plural = "Subscription Feature Usages"
    
    def __str__(self):
        return f"{self.user.username} - {self.feature_name} ({self.usage_count})"


class ExpiredSubscriptionAction(models.Model):
    """Scheduled actions for expired subscriptions"""
    
    ACTION_TYPES = [
        ('revoke_access', 'Revoke Access'),
        ('downgrade_tier', 'Downgrade Tier'),
        ('send_notification', 'Send Notification'),
        ('archive_data', 'Archive Data'),
        ('force_subscription', 'Force Subscription'),
    ]
    
    ACTION_STATUSES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name='scheduled_actions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscription_actions')
    
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES)
    action_status = models.CharField(max_length=20, choices=ACTION_STATUSES, default='pending')
    action_data = models.JSONField(default=dict, blank=True)
    
    scheduled_at = models.DateTimeField()
    executed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['scheduled_at']
        verbose_name = "Expired Subscription Action"
        verbose_name_plural = "Expired Subscription Actions"
    
    def __str__(self):
        return f"{self.user.username} - {self.action_type} ({self.action_status})"


class TrialPopupLog(models.Model):
    """Track trial popup interactions"""
    
    USER_ACTIONS = [
        ('subscribe', 'Subscribe'),
        ('dismiss', 'Dismiss'),
        ('later', 'Maybe Later'),
        ('view_tiers', 'View Tiers'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='popup_logs')
    
    trigger_action = models.CharField(max_length=100)  # like, comment, follow, etc.
    trigger_screen = models.CharField(max_length=100)  # home, reels, profile, etc.
    popup_shown = models.BooleanField(default=True)
    user_action = models.CharField(max_length=50, choices=USER_ACTIONS, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Trial Popup Log"
        verbose_name_plural = "Trial Popup Logs"
    
    def __str__(self):
        return f"{self.user.username} - {self.trigger_action} ({self.user_action or 'No Action'})"


class SubscriptionCoinTransaction(models.Model):
    """Coin transactions for OnDemand and other coin-based features"""
    
    TRANSACTION_TYPES = [
        ('purchase', 'Purchase'),
        ('subscription', 'Subscription'),
        ('refund', 'Refund'),
        ('bonus', 'Bonus'),
        ('gift', 'Gift'),
        ('transfer', 'Transfer'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscription_coin_transactions')
    
    transaction_type = models.CharField(max_length=50, choices=TRANSACTION_TYPES)
    amount = models.IntegerField(help_text='Coin amount (positive or negative)')
    balance_after = models.IntegerField(help_text='Balance after transaction')
    
    description = models.TextField(blank=True)
    reference_id = models.CharField(max_length=100, null=True, blank=True)
    reference_type = models.CharField(max_length=50, null=True, blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['transaction_type', '-created_at']),
        ]
        verbose_name = "Coin Transaction"
        verbose_name_plural = "Coin Transactions"
    
    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} ({self.amount} coins)"


class AdminRole(models.Model):
    """Admin role definitions"""
    
    ROLE_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('support_agent', 'Support Agent'),
        ('finance_team', 'Finance Team'),
        ('content_moderator', 'Content Moderator'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_role')
    role = models.CharField(max_length=50, choices=ROLE_CHOICES)
    
    permissions = models.JSONField(default=dict, blank=True, help_text='Custom permissions override')
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Admin Role"
        verbose_name_plural = "Admin Roles"
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
    
    def has_permission(self, permission):
        """Check if admin has specific permission"""
        if self.role == 'super_admin':
            return True
        
        role_permissions = {
            'support_agent': [
                'view_subscriptions', 'view_users', 'view_reports'
            ],
            'finance_team': [
                'view_revenue', 'view_payments', 'export_reports'
            ],
            'content_moderator': [
                'view_content', 'moderate_content', 'view_users'
            ],
        }
        
        return permission in role_permissions.get(self.role, []) or permission in self.permissions.get('custom', [])


class SubscriptionReport(models.Model):
    """Generated subscription reports"""
    
    REPORT_TYPES = [
        ('daily_revenue', 'Daily Revenue'),
        ('monthly_subscription', 'Monthly Subscription'),
        ('custom', 'Custom Date Range'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPES)
    title = models.CharField(max_length=255)
    
    date_from = models.DateField()
    date_to = models.DateField()
    
    data = models.JSONField()
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='generated_reports')
    
    file_csv = models.FileField(upload_to='reports/csv/', null=True, blank=True)
    file_pdf = models.FileField(upload_to='reports/pdf/', null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Subscription Report"
        verbose_name_plural = "Subscription Reports"
    
    def __str__(self):
        return f"{self.title} - {self.date_from} to {self.date_to}"


class OnevasChargingTransaction(models.Model):
    """Onevas on-demand charging transactions for subscriptions"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('insufficient_balance', 'Insufficient Balance'),
        ('timeout', 'Timeout'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='charging_transactions')
    
    phone_number = models.CharField(max_length=20, help_text='User phone number for charging')
    product_number = models.CharField(max_length=50, help_text='Onevas product number')
    application_key = models.CharField(max_length=100, help_text='Onevas application key used')
    
    subscription_tier = models.ForeignKey(SubscriptionTier, on_delete=models.SET_NULL, null=True, related_name='charging_transactions')
    
    amount_etb = models.DecimalField(max_digits=10, decimal_places=2, help_text='Amount charged in ETB')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    
    # Onevas response
    transaction_id = models.CharField(max_length=100, blank=True, null=True, help_text='Onevas transaction ID')
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    
    # Webhook data
    webhook_received = models.BooleanField(default=False)
    webhook_payload = models.JSONField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Onevas Charging Transaction"
        verbose_name_plural = "Onevas Charging Transactions"
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['phone_number']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.amount_etb} ETB - {self.status}"
