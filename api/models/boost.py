from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal


class BoostConfig(models.Model):
    """Platform-wide boost configuration and pricing"""
    
    # Base pricing (coins per hour)
    # Duration tiers:
    # 1 Hour: 50 coins
    # 6 Hours: 250 coins (17% discount)
    # 12 Hours: 400 coins (33% discount)
    # 24 Hours: 700 coins (42% discount)
    # 3 Days (72 hours): 1,500 coins (56% discount)
    # 7 Days (168 hours): 2,500 coins (71% discount)
    
    base_hourly_rate = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('50.00'),
        help_text='Base cost per hour in coins'
    )
    
    # Discount tiers (percentage off)
    discount_6hr = models.IntegerField(default=17, help_text='Discount % for 6-hour boost')
    discount_12hr = models.IntegerField(default=33, help_text='Discount % for 12-hour boost')
    discount_24hr = models.IntegerField(default=42, help_text='Discount % for 24-hour boost')
    discount_3day = models.IntegerField(default=56, help_text='Discount % for 3-day boost')
    discount_7day = models.IntegerField(default=71, help_text='Discount % for 7-day boost')
    
    # Impression rate (how many impressions per coin)
    base_impression_rate = models.IntegerField(
        default=10,
        help_text='Base impressions per coin (1 coin = X impressions)'
    )
    
    # Platform fee
    platform_fee_percent = models.IntegerField(
        default=10,
        help_text='Platform fee percentage on top of boost cost'
    )
    
    # Pacing settings
    pacing_tolerance = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        default=Decimal('1.20'),
        help_text='Allow 20% over-spend tolerance'
    )
    
    # Duration limits
    min_duration_hours = models.IntegerField(default=1, help_text='Minimum boost duration in hours')
    max_duration_hours = models.IntegerField(default=168, help_text='Maximum boost duration in hours (7 days)')
    
    # Injection ratio (1 boost per X organic posts)
    injection_ratio = models.IntegerField(default=4, help_text='1 boost per X organic posts')
    
    # Frequency capping
    frequency_cap_hours = models.IntegerField(default=12, help_text='Hours before same user can see same boost again')
    
    # User limits
    max_daily_boosts_per_user = models.IntegerField(default=5, help_text='Max boosts per day per user')
    max_active_boosts_per_post = models.IntegerField(default=3, help_text='Max concurrent boosts per post')
    
    # Premium targeting surcharge
    premium_targeting_surcharge = models.IntegerField(
        default=20,
        help_text='Additional % cost for premium targeting (age/gender/location)'
    )
    
    # Refund policy
    refund_threshold_percent = models.IntegerField(
        default=50,
        help_text='If less than X% of expected impressions served, refund X%'
    )
    
    cancellation_fee_percent = models.IntegerField(
        default=10,
        help_text='Cancellation fee percentage of remaining budget'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Boost Configuration'
        verbose_name_plural = 'Boost Configurations'
    
    def __str__(self):
        return f"Boost Config (Hourly Rate: {self.base_hourly_rate} coins)"
    
    def calculate_cost(self, duration_hours, has_premium_targeting=False):
        """Calculate boost cost based on duration and targeting"""
        base_cost = self.base_hourly_rate * duration_hours
        
        # Apply duration discount
        if duration_hours == 6:
            discount = self.discount_6hr
        elif duration_hours == 12:
            discount = self.discount_12hr
        elif duration_hours == 24:
            discount = self.discount_24hr
        elif duration_hours == 72:
            discount = self.discount_3day
        elif duration_hours == 168:
            discount = self.discount_7day
        else:
            discount = 0
        
        discounted_cost = base_cost * (Decimal('1') - Decimal(discount) / Decimal('100'))
        
        # Add premium targeting surcharge
        if has_premium_targeting:
            discounted_cost = discounted_cost * (Decimal('1') + Decimal(self.premium_targeting_surcharge) / Decimal('100'))
        
        # Add platform fee
        final_cost = discounted_cost * (Decimal('1') + Decimal(self.platform_fee_percent) / Decimal('100'))
        
        return final_cost.quantize(Decimal('0.01'))
    
    def get_expected_impressions(self, cost):
        """Calculate expected impressions based on cost"""
        return int(cost * self.base_impression_rate)


class BoostCampaign(models.Model):
    """Individual boost campaign for a post"""
    
    DURATION_CHOICES = [
        (1, '1 Hour'),
        (6, '6 Hours'),
        (12, '12 Hours'),
        (24, '24 Hours'),
        (72, '3 Days'),
        (168, '7 Days'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('exhausted', 'Budget Exhausted'),
        # A guaranteed campaign whose window closed before its guarantee was
        # met. Distinct from 'completed' on purpose: Viral sells 5,000
        # impressions, and a campaign that served 2,000 must not be
        # indistinguishable from one that served all of them. What is owed
        # is decided by a person; what happened is recorded here.
        ('undelivered', 'Ended Below Guarantee'),
    ]
    
    BOOST_TYPE_CHOICES = [
        ('standard', 'Standard'),
        ('premium', 'Premium'),
        ('viral', 'Viral'),
        ('custom', 'Custom (hourly)'),
    ]

    PLACEMENT_CHOICES = [
        ('trending', 'Top of Trending'),
        ('feed', 'Top of the feed'),
        ('everywhere', 'Trending and the feed'),
    ]

    # Core relationships
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='boost_campaigns')
    reel = models.ForeignKey('Reel', on_delete=models.CASCADE, related_name='boost_campaigns')

    # Which product was bought. 'custom' is what every campaign predating the
    # three named tiers was: priced by the hour from BoostConfig rather than
    # from a fixed tier, and placed in Trending because that was the only
    # feed reading the boost state at the time.
    boost_type = models.CharField(max_length=20, choices=BOOST_TYPE_CHOICES, default='custom')
    placement = models.CharField(max_length=20, choices=PLACEMENT_CHOICES, default='trending')

    # Only Viral carries one. NULL rather than 0 for the others, so nothing
    # can render "0 guaranteed impressions" or treat an absent guarantee as a
    # promise of none -- see api/services/boost_tiers.py.
    guaranteed_impressions = models.PositiveIntegerField(null=True, blank=True)

    # Budget & Duration
    duration_hours = models.IntegerField(choices=DURATION_CHOICES)
    coins_spent = models.DecimalField(max_digits=10, decimal_places=2)
    coins_remaining = models.DecimalField(max_digits=10, decimal_places=2)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField()
    
    # Expected reach
    expected_impressions = models.IntegerField(help_text='Expected impressions based on cost')
    impressions_served = models.IntegerField(default=0)
    
    # Engagement tracking
    engagement_count = models.IntegerField(default=0, help_text='Total engagements (likes + comments + shares)')
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Targeting (optional premium features)
    target_gender = models.CharField(
        max_length=10, 
        blank=True, 
        null=True,
        choices=[('male', 'Male'), ('female', 'Female'), ('all', 'All')],
        help_text='Target audience gender'
    )
    target_age_min = models.IntegerField(null=True, blank=True, help_text='Minimum age')
    target_age_max = models.IntegerField(null=True, blank=True, help_text='Maximum age')
    target_location = models.CharField(max_length=100, blank=True, help_text='Target city/region')
    
    # Pacing
    hourly_budget = models.DecimalField(max_digits=10, decimal_places=2, help_text='Coins per hour budget')
    last_pacing_check = models.DateTimeField(auto_now=True)
    
    # Cancellation
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    
    # Refund tracking
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    refunded_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['reel', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['end_time']),
        ]
        constraints = [
            # One live tier boost per post, enforced by the database.
            #
            # The view checks too, but a check is a race: two concurrent
            # requests both read "no active boost" and both create one, and
            # both are charged -- 2,000 coins for a single Viral placement.
            # A partial unique index is what actually makes it impossible;
            # the check just turns the second request into a friendly 400
            # instead of an IntegrityError.
            #
            # Scoped to the named tiers. The older hourly form has always
            # allowed several concurrent boosts on a post
            # (BoostConfig.max_active_boosts_per_post, default 3), and
            # narrowing that retroactively would cancel behaviour people
            # already rely on -- and would fail this migration against any
            # post that currently has two.
            models.UniqueConstraint(
                fields=['reel'],
                condition=models.Q(status='active') & ~models.Q(boost_type='custom'),
                name='one_active_tier_boost_per_reel',
            ),
        ]
    
    def __str__(self):
        return f"Boost #{self.id} - {self.user.username} - {self.duration_hours}h"
    
    def save(self, *args, **kwargs):
        if not self.end_time:
            from datetime import timedelta
            self.end_time = self.start_time + timedelta(hours=self.duration_hours)
        super().save(*args, **kwargs)
    
    def is_active(self):
        """Check if campaign is currently active"""
        return (
            self.status == 'active' and
            timezone.now() < self.end_time and
            self.coins_remaining > 0
        )
    
    def get_progress_percent(self):
        """Get campaign progress as percentage"""
        if self.coins_spent == 0:
            return 0
        total = self.coins_spent + self.coins_remaining
        if total == 0:
            return 0
        return int((self.coins_spent / total) * 100)
    
    def get_time_remaining(self):
        """Get remaining time in hours"""
        if timezone.now() >= self.end_time:
            return 0
        return int((self.end_time - timezone.now()).total_seconds() / 3600)


class BoostImpression(models.Model):
    """Track which users saw which boosted posts (for frequency capping)"""
    
    campaign = models.ForeignKey(BoostCampaign, on_delete=models.CASCADE, related_name='impressions')
    viewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='boost_impressions')
    viewed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['campaign', 'viewer']
        indexes = [
            models.Index(fields=['campaign', 'viewer']),
            models.Index(fields=['viewer', 'viewed_at']),
        ]
    
    def __str__(self):
        return f"{self.viewer.username} viewed boost #{self.campaign.id}"


class BoostEngagement(models.Model):
    """Track engagements on boosted posts (likes, comments, shares)"""
    
    ENGAGEMENT_TYPES = [
        ('like', 'Like'),
        ('comment', 'Comment'),
        ('share', 'Share'),
    ]
    
    campaign = models.ForeignKey(BoostCampaign, on_delete=models.CASCADE, related_name='engagements')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='boost_engagements')
    engagement_type = models.CharField(max_length=20, choices=ENGAGEMENT_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['campaign', 'engagement_type']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} {self.engagement_type} on boost #{self.campaign.id}"


class BoostStats(models.Model):
    """Daily aggregated statistics for boost campaigns"""
    
    campaign = models.ForeignKey(BoostCampaign, on_delete=models.CASCADE, related_name='daily_stats')
    date = models.DateField()
    
    # Daily metrics
    impressions_served = models.IntegerField(default=0)
    engagements = models.IntegerField(default=0)
    coins_spent = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # Hourly breakdown (JSON)
    hourly_breakdown = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['campaign', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['campaign', '-date']),
            models.Index(fields=['date']),
        ]
    
    def __str__(self):
        return f"Stats for boost #{self.campaign.id} on {self.date}"
