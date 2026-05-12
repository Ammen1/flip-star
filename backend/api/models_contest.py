"""
90-Day Contest System Models
Core database structure for tiered subscriptions, coin economy, and scoring
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class UserTier(models.TextChoices):
    """Four-tier subscription system"""
    FREE = 'free', 'Free (1 post/day)'
    SILVER = 'silver', 'Silver (3 posts/day, 1.5x points)'
    GOLD = 'gold', 'Gold (Unlimited, 2x points)'
    VIP = 'vip', 'VIP (Unlimited, 3x points, Annual)'


class UserSubscription(models.Model):
    """
    User subscription with tier-based multipliers
    Monthly auto-renewal (30 days), VIP is annual
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='contest_subscription')
    tier = models.CharField(max_length=20, choices=UserTier.choices, default=UserTier.FREE)
    
    # Subscription timing
    start_date = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    auto_renew = models.BooleanField(default=True)
    
    # Payment info
    last_payment_date = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True)  # 'telebirr', 'airtime', 'coins'
    
    # Usage tracking (resets daily)
    posts_today = models.PositiveIntegerField(default=0)
    last_post_date = models.DateField(null=True, blank=True)
    
    # Streak tracking
    post_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_subscriptions'

    def get_daily_post_limit(self):
        """Get daily post limit based on tier"""
        limits = {
            'free': 1,
            'silver': 3,
            'gold': float('inf'),  # Unlimited
            'vip': float('inf'),   # Unlimited
        }
        return limits.get(self.tier, 1)

    def get_score_multiplier(self):
        """Get point multiplier based on tier"""
        multipliers = {
            'free': 1.0,
            'silver': 1.5,
            'gold': 2.0,
            'vip': 3.0,
        }
        return multipliers.get(self.tier, 1.0)

    def can_post_today(self):
        """Check if user can post today based on tier limits"""
        limit = self.get_daily_post_limit()
        if limit == float('inf'):
            return True
        
        today = timezone.now().date()
        if self.last_post_date != today:
            self.posts_today = 0
            self.last_post_date = today
            self.save(update_fields=['posts_today', 'last_post_date'])
        
        return self.posts_today < limit

    def record_post(self):
        """Record a post and update streak"""
        today = timezone.now().date()
        
        # Update streak
        if self.last_post_date:
            yesterday = today - timedelta(days=1)
            if self.last_post_date == yesterday:
                self.post_streak += 1
            elif self.last_post_date != today:
                self.post_streak = 1
        else:
            self.post_streak = 1
        
        # Update longest streak
        if self.post_streak > self.longest_streak:
            self.longest_streak = self.post_streak
        
        # Update posts today
        if self.last_post_date != today:
            self.posts_today = 1
            self.last_post_date = today
        else:
            self.posts_today += 1
        
        self.save(update_fields=['posts_today', 'last_post_date', 'post_streak', 'longest_streak'])

    def is_expired(self):
        """Check if subscription has expired"""
        return timezone.now() > self.expires_at

    def renew(self):
        """Renew subscription for another period"""
        if self.tier == UserTier.VIP:
            # Annual renewal
            self.expires_at = timezone.now() + timedelta(days=365)
        else:
            # Monthly renewal
            self.expires_at = timezone.now() + timedelta(days=30)
        
        self.last_payment_date = timezone.now()
        self.save(update_fields=['expires_at', 'last_payment_date'])


class CoinPackage(models.Model):
    """
    Coin purchase packages (10 ETB to 500 ETB)
    """
    name = models.CharField(max_length=50)
    price_etb = models.DecimalField(max_digits=10, decimal_places=2)
    coin_amount = models.PositiveIntegerField()
    bonus_coins = models.PositiveIntegerField(default=0)
    
    # Package features
    is_featured = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'coin_packages'
        ordering = ['sort_order', 'price_etb']

    def __str__(self):
        return f"{self.name} - {self.coin_amount} coins ({self.price_etb} ETB)"

    def get_total_coins(self):
        """Total coins including bonus"""
        return self.coin_amount + self.bonus_coins


class CoinTransaction(models.Model):
    """
    Coin purchase and spending transactions
    """
    TRANSACTION_TYPES = [
        ('purchase', 'Purchase (Telebirr)'),
        ('welcome_bonus', 'Welcome Bonus'),
        ('daily_login', 'Daily Login Bonus'),
        ('spin_reward', 'Daily Spin Reward'),
        ('post_bonus', 'Daily Post Bonus'),
        ('campaign_join', 'Campaign Join Reward'),
        ('campaign_winner', 'Campaign Winner Reward'),
        ('like_received', 'Like Received'),
        ('comment_reward', 'Quality Comment Reward'),
        ('referral', 'Referral Bonus'),
        ('profile_complete', 'Profile Completion'),
        ('gift_sent', 'Gift Sent'),
        ('gift_received', 'Gift Received'),
        ('boost', 'Post Boost'),
        ('extra_entry', 'Extra Entry'),
        ('reward', 'Generic Reward'),
        ('refund', 'Refund'),
        ('withdrawal', 'Withdrawal to Birr'),
        ('admin_adjustment', 'Admin Adjustment'),
    ]
    
    PAYMENT_METHODS = [
        ('telebirr', 'Telebirr'),
        ('airtime', 'Airtime'),
        ('coins', 'Coins'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='coin_transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    
    # Amount (positive for credit, negative for debit)
    coins = models.IntegerField()
    
    # For purchases
    package = models.ForeignKey(CoinPackage, on_delete=models.SET_NULL, null=True, blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)  # Telebirr transaction ID
    
    # For spending
    recipient = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='coin_gifts_received')
    reel = models.ForeignKey('Reel', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Fee tracking (e.g., 5% for airtime)
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    description = models.CharField(max_length=255, blank=True)
    is_successful = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'coin_transactions'
        ordering = ['-created_at']


class UserCoinBalance(models.Model):
    """
    Current coin balance for each user.

    Two buckets:
    - earned_balance: from rewards (login, spin, post, campaign). Restricted use.
    - purchased_balance: bought via Telebirr. Full use including gifting.

    `balance` field = earned + purchased (kept for backward compatibility).
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='coin_balance')

    # Legacy total balance (kept for backward compat). Always = earned + purchased.
    balance = models.PositiveIntegerField(default=0)

    # New split buckets
    earned_balance = models.PositiveIntegerField(default=0, help_text='From rewards. Cannot be gifted.')
    purchased_balance = models.PositiveIntegerField(default=0, help_text='Bought via Telebirr. Full use.')

    total_earned = models.PositiveIntegerField(default=0)
    total_spent = models.PositiveIntegerField(default=0)
    total_purchased = models.PositiveIntegerField(default=0, help_text='Lifetime coins bought')
    total_withdrawn = models.PositiveIntegerField(default=0, help_text='Lifetime coins withdrawn to Birr')

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_coin_balances'

    def _sync_balance(self):
        """Keep legacy `balance` field in sync with the two buckets."""
        self.balance = (self.earned_balance or 0) + (self.purchased_balance or 0)

    def add_earned(self, amount, transaction_type='reward', **kwargs):
        """Add coins to earned balance (rewards, spin, login, etc.)"""
        if amount <= 0:
            raise ValueError('Amount must be positive')
        self.earned_balance = (self.earned_balance or 0) + amount
        self.total_earned += amount
        self._sync_balance()
        self.save(update_fields=['earned_balance', 'balance', 'total_earned', 'updated_at'])

        return CoinTransaction.objects.create(
            user=self.user,
            transaction_type=transaction_type,
            coins=amount,
            **kwargs
        )

    def add_purchased(self, amount, transaction_type='purchase', **kwargs):
        """Add coins to purchased balance (Telebirr top-ups)"""
        if amount <= 0:
            raise ValueError('Amount must be positive')
        self.purchased_balance = (self.purchased_balance or 0) + amount
        self.total_purchased += amount
        self._sync_balance()
        self.save(update_fields=['purchased_balance', 'balance', 'total_purchased', 'updated_at'])

        return CoinTransaction.objects.create(
            user=self.user,
            transaction_type=transaction_type,
            coins=amount,
            **kwargs
        )

    def add_coins(self, amount, transaction_type='reward', **kwargs):
        """Backward-compatible: defaults to earned bucket unless type is purchase."""
        if transaction_type == 'purchase':
            return self.add_purchased(amount, transaction_type, **kwargs)
        return self.add_earned(amount, transaction_type, **kwargs)

    def spend_coins(self, amount, transaction_type, restrict_earned=False, **kwargs):
        """
        Spend coins from balance.

        - If restrict_earned=True (e.g., gifting): can only use purchased_balance.
        - Otherwise: prefer earned_balance first, then purchased_balance.
        """
        if amount <= 0:
            raise ValueError('Amount must be positive')

        if restrict_earned:
            # Gifting: only purchased coins allowed
            if (self.purchased_balance or 0) < amount:
                raise ValueError(
                    f'Insufficient purchased coins. Have {self.purchased_balance}, need {amount}. '
                    'Earned coins cannot be used for gifting. Top up via Telebirr.'
                )
            self.purchased_balance -= amount
        else:
            # In-app actions: prefer earned, fall back to purchased
            total = (self.earned_balance or 0) + (self.purchased_balance or 0)
            if total < amount:
                raise ValueError(f'Insufficient balance. Have {total}, need {amount}')

            from_earned = min(self.earned_balance or 0, amount)
            from_purchased = amount - from_earned
            self.earned_balance -= from_earned
            self.purchased_balance -= from_purchased

        self.total_spent += amount
        self._sync_balance()
        self.save(update_fields=[
            'earned_balance', 'purchased_balance', 'balance', 'total_spent', 'updated_at'
        ])

        return CoinTransaction.objects.create(
            user=self.user,
            transaction_type=transaction_type,
            coins=-amount,
            **kwargs
        )

    def withdraw_to_birr(self, amount):
        """Deduct coins for a withdrawal request (only earned coins by default)."""
        if amount <= 0:
            raise ValueError('Amount must be positive')
        if (self.earned_balance or 0) < amount:
            raise ValueError(f'Insufficient earned coins. Have {self.earned_balance}, need {amount}')
        self.earned_balance -= amount
        self.total_withdrawn += amount
        self._sync_balance()
        self.save(update_fields=[
            'earned_balance', 'balance', 'total_withdrawn', 'updated_at'
        ])

        return CoinTransaction.objects.create(
            user=self.user,
            transaction_type='withdrawal',
            coins=-amount,
            description='Withdrawal to Birr (pending review)'
        )


class PostBoost(models.Model):
    """
    Boosted posts (200 coins for 2 hours featured)
    """
    reel = models.OneToOneField('Reel', on_delete=models.CASCADE, related_name='boost')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    boosted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    cost_coins = models.PositiveIntegerField(default=200)
    
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'post_boosts'

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=2)
        super().save(*args, **kwargs)

    def is_boost_active(self):
        """Check if boost is still active"""
        return self.is_active and timezone.now() < self.expires_at


class GiftToCreator(models.Model):
    """
    Gift coins to creators (+5 bonus points to recipient)
    """
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contest_gifts_sent')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contest_gifts_received')
    reel = models.ForeignKey('Reel', on_delete=models.CASCADE, null=True, blank=True)
    
    coins = models.PositiveIntegerField()
    bonus_points = models.PositiveIntegerField(default=5)
    message = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gifts_to_creators'


# Scoring Matrix Models

class ContestPostScore(models.Model):
    """
    Total score for each post (max 100 points)
    Components: Creativity(30), Engagement(25), Consistency(20), Quality(15), Theme(10)
    """
    reel = models.OneToOneField('Reel', on_delete=models.CASCADE, related_name='contest_score')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Admin-assigned scores (manual)
    creativity = models.PositiveIntegerField(default=0, help_text="Max 30 points")
    quality = models.PositiveIntegerField(default=0, help_text="Max 15 points")
    theme_relevance = models.PositiveIntegerField(default=0, help_text="Max 10 points")
    
    # Automated scores
    engagement = models.PositiveIntegerField(default=0, help_text="Max 25 points - from likes/shares")
    consistency = models.PositiveIntegerField(default=0, help_text="Max 20 points - from streaks")
    
    # Final calculated score
    total_score = models.PositiveIntegerField(default=0)
    
    # Judging status
    is_judged = models.BooleanField(default=False)
    judged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='judged_scores')
    judged_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    likes_at_judging = models.PositiveIntegerField(default=0)
    shares_at_judging = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contest_post_scores'
        ordering = ['-total_score']

    def calculate_total(self):
        """Calculate total score with tier multiplier"""
        base_score = min(self.creativity, 30) + min(self.engagement, 25) + \
                     min(self.consistency, 20) + min(self.quality, 15) + \
                     min(self.theme_relevance, 10)
        
        # Apply tier multiplier
        try:
            multiplier = self.user.subscription.get_score_multiplier()
        except:
            multiplier = 1.0
        
        self.total_score = min(int(base_score * multiplier), 100)
        return self.total_score

    def calculate_engagement(self, likes, shares):
        """Calculate engagement score based on likes and shares"""
        # Engagement formula: likes + (shares * 2), max 25
        score = min((likes + shares * 2) // 10, 25)
        self.engagement = score
        return score

    def calculate_consistency(self, streak):
        """Calculate consistency score based on post streak"""
        # Consistency: streak >= 7 = 20 points, else streak * 2
        if streak >= 7:
            score = 20
        else:
            score = min(streak * 2, 20)
        self.consistency = score
        return score


class ContestLeaderboard(models.Model):
    """
    Daily, Weekly, Monthly leaderboards for contests
    """
    PERIOD_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('grand', 'Grand Finale'),
    ]
    
    period = models.CharField(max_length=20, choices=PERIOD_CHOICES)
    date = models.DateField()  # For daily; for weekly/monthly use start date
    
    # Top entries for this period
    entries = models.JSONField(default=list)  # [{user_id, username, score, rank}, ...]
    
    # Winners (if applicable)
    winners = models.JSONField(default=list)
    
    is_finalized = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'contest_leaderboards'
        unique_together = ['period', 'date']
        ordering = ['-date']


class ContestTimeline(models.Model):
    """
    90-day contest timeline with countdown
    """
    name = models.CharField(max_length=100)  # e.g., "Summer Contest 2024"
    
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()  # 90 days from start
    
    # Budget tracking (2.1 Million ETB total)
    total_budget = models.DecimalField(max_digits=12, decimal_places=2, default=2100000)
    daily_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    weekly_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monthly_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    grand_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Spending tracking
    spent_daily = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    spent_weekly = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    spent_monthly = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    spent_grand = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Flash challenge settings
    flash_multiplier = models.FloatField(default=1.5)
    flash_start_time = models.TimeField(null=True, blank=True)
    flash_end_time = models.TimeField(null=True, blank=True)
    is_flash_active = models.BooleanField(default=False)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'contest_timelines'

    def get_days_remaining(self):
        """Get days remaining in contest"""
        if timezone.now() > self.end_date:
            return 0
        delta = self.end_date - timezone.now()
        return delta.days

    def get_budget_breakdown(self):
        """Get budget allocation percentages"""
        return {
            'daily': 30,      # 30% daily
            'weekly': 25,     # 25% weekly
            'monthly': 25,    # 25% monthly
            'grand': 20,      # 20% grand finale
        }

    def is_flash_hour(self):
        """Check if current time is flash hour"""
        if not self.is_flash_active:
            return False
        
        now = timezone.now().time()
        if self.flash_start_time and self.flash_end_time:
            return self.flash_start_time <= now <= self.flash_end_time
        return False


class AntiCheatLog(models.Model):
    """
    Fake engagement detection and flagging
    """
    FLAG_TYPES = [
        ('like_spam', 'Like Spam (>100/min)'),
        ('follow_spam', 'Follow Spam'),
        ('vote_spam', 'Vote Spam'),
        ('suspicious', 'Suspicious Activity'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('cleared', 'Cleared'),
        ('confirmed', 'Confirmed Fraud'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flags')
    flag_type = models.CharField(max_length=20, choices=FLAG_TYPES)
    
    # Details
    description = models.TextField()
    evidence = models.JSONField(default=dict)  # {likes_per_minute, timestamps, etc.}
    
    # Affected content
    reel = models.ForeignKey('Reel', on_delete=models.SET_NULL, null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviews')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'anti_cheat_logs'
        ordering = ['-created_at']


class EligibilityVerification(models.Model):
    """
    Age 18+ and verified phone number requirements
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='eligibility')
    
    # Phone verification (Ethio Telecom)
    phone_number = models.CharField(max_length=20, blank=True)
    is_phone_verified = models.BooleanField(default=False)
    verification_code = models.CharField(max_length=10, blank=True)
    
    # Age verification
    date_of_birth = models.DateField(null=True, blank=True)
    is_age_verified = models.BooleanField(default=False)
    age_verification_method = models.CharField(max_length=50, blank=True)
    
    # Document uploads
    id_document = models.ImageField(upload_to='verification/ids/', null=True, blank=True)
    selfie_with_id = models.ImageField(upload_to='verification/selfies/', null=True, blank=True)
    
    # Status
    is_fully_verified = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='eligibility_reviews')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'eligibility_verifications'

    def check_eligibility(self):
        """Check if user is eligible (18+ and phone verified)"""
        if not self.is_phone_verified:
            return False, "Phone number not verified"
        
        if not self.date_of_birth:
            return False, "Age not verified"
        
        age = (timezone.now().date() - self.date_of_birth).days // 365
        if age < 18:
            return False, "Must be 18 or older"
        
        self.is_fully_verified = True
        self.save(update_fields=['is_fully_verified'])
        return True, "Eligible"


class GrandFinaleEntry(models.Model):
    """
    Day 90 Grand Finale entries
    Combined scoring: Judge scores (70%) + Public Coin Votes (30%)
    """
    contest = models.ForeignKey(ContestTimeline, on_delete=models.CASCADE, related_name='grand_entries')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reel = models.ForeignKey('Reel', on_delete=models.CASCADE)
    
    # Judge scoring (70% weight)
    judge_creativity = models.PositiveIntegerField(default=0)
    judge_quality = models.PositiveIntegerField(default=0)
    judge_theme = models.PositiveIntegerField(default=0)
    judge_total = models.PositiveIntegerField(default=0)
    
    # Public voting (30% weight)
    public_votes = models.PositiveIntegerField(default=0)
    coins_received = models.PositiveIntegerField(default=0)
    
    # Final combined score
    final_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    rank = models.PositiveIntegerField(null=True, blank=True)
    
    is_winner = models.BooleanField(default=False)
    prize_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'grand_finale_entries'
        ordering = ['-final_score']

    def calculate_final_score(self):
        """Calculate final score: 70% judge + 30% public votes"""
        judge_weight = 0.7
        public_weight = 0.3
        
        # Normalize judge score to 100
        judge_score = min(self.judge_total, 100)
        
        # Normalize public votes (this would need to be relative to top voter)
        # For now, cap at 100
        public_score = min(self.public_votes, 100)
        
        self.final_score = (judge_score * judge_weight) + (public_score * public_weight)
        return self.final_score


class ExtraEntryPurchase(models.Model):
    """
    Purchase extra post entries beyond daily limit (100 coins)
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    extra_entries_purchased = models.PositiveIntegerField(default=1)
    coins_spent = models.PositiveIntegerField(default=100)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'extra_entry_purchases'
        unique_together = ['user', 'date']
