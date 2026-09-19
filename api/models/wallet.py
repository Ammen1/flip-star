"""
Wallet System Models

- WalletConfig: Admin-configurable singleton for coin economy settings
- WithdrawalRequest: Users requesting to convert coins -> Ethiopian Birr (ETB)

Note: UserCoinBalance, CoinTransaction, CoinPackage already exist in models.contest.py
This module extends the wallet ecosystem.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class WalletConfig(models.Model):
    """
    Singleton model for admin-configurable coin economy settings.
    Only one row should exist (id=1).
    """

    # ============ EARNING REWARDS ============
    welcome_bonus = models.PositiveIntegerField(
        default=100, help_text='Coins given to new users on signup'
    )
    daily_login_day1 = models.PositiveIntegerField(default=5)
    daily_login_day2 = models.PositiveIntegerField(default=10)
    daily_login_day3 = models.PositiveIntegerField(default=15)
    daily_login_day4 = models.PositiveIntegerField(default=20)
    daily_login_day5 = models.PositiveIntegerField(default=25)
    daily_login_day6 = models.PositiveIntegerField(default=30)
    daily_login_day7 = models.PositiveIntegerField(default=50)

    daily_post_bonus = models.PositiveIntegerField(
        default=20, help_text='Coins for first post of the day'
    )
    campaign_join_reward = models.PositiveIntegerField(
        default=30, help_text='Coins for joining a campaign'
    )
    receive_like_reward = models.PositiveIntegerField(
        default=1, help_text='Coins per like received'
    )
    receive_like_daily_cap = models.PositiveIntegerField(
        default=100, help_text='Max coins/day from likes'
    )
    quality_comment_reward = models.PositiveIntegerField(
        default=2, help_text='Coins per long comment'
    )
    quality_comment_daily_cap = models.PositiveIntegerField(default=20)
    profile_complete_reward = models.PositiveIntegerField(default=50, help_text='One-time reward')
    referral_reward = models.PositiveIntegerField(default=100, help_text='Coins per friend signup')
    campaign_winner_reward = models.PositiveIntegerField(
        default=500, help_text='Bonus for winning a campaign'
    )

    # ============ ACTION COSTS ============
    # ── Platform ceilings for organization coin configuration ───────────────
    # Super Admin's safety boundary: an organization may set its own reward
    # rates, but not above these. Enforced in
    # api/services/coin_config.validate_against_platform_limits, which the
    # model's clean() calls -- so the admin, the API and a management command
    # all refuse the same values.
    max_like_reward = models.PositiveIntegerField(
        default=10, help_text='Most coins an organization may pay per like.'
    )
    max_comment_reward = models.PositiveIntegerField(
        default=20, help_text='Most coins an organization may pay per comment.'
    )
    max_share_reward = models.PositiveIntegerField(
        default=50, help_text='Most coins an organization may pay per share.'
    )
    max_gift_reward = models.PositiveIntegerField(
        default=100, help_text='Most coins an organization may pay per gift.'
    )

    cost_post_create = models.PositiveIntegerField(
        default=0, help_text='Cost to create a post (0 = free)'
    )
    cost_like = models.PositiveIntegerField(
        default=0, help_text='Coins charged when liking a campaign post (0 = free)'
    )
    cost_comment = models.PositiveIntegerField(
        default=0, help_text='Coins charged when commenting on a campaign post (0 = free)'
    )
    cost_share = models.PositiveIntegerField(
        default=0, help_text='Coins charged when sharing a campaign post (0 = free)'
    )
    cost_gift = models.PositiveIntegerField(
        default=0,
        help_text='Extra coins charged on top of gift value when gifting on a campaign post (0 = free)',
    )
    cost_join_campaign = models.PositiveIntegerField(default=50)
    cost_extra_campaign_entry = models.PositiveIntegerField(default=100)
    cost_boost_1hr = models.PositiveIntegerField(
        default=100, help_text='Cost to boost post for 1 hour'
    )
    cost_boost_2hr = models.PositiveIntegerField(default=200)
    cost_boost_24hr = models.PositiveIntegerField(default=800)
    cost_trending_1hr = models.PositiveIntegerField(
        default=150, help_text='Cost to make post trending for 1 hour'
    )
    cost_trending_24hr = models.PositiveIntegerField(
        default=1200, help_text='Cost to make post trending for 24 hours'
    )
    cost_post_create_long_video = models.PositiveIntegerField(
        default=0, help_text='Additional coins for campaign videos > 60 seconds (0 = free)'
    )

    # ============ NON-CAMPAIGN ACTION COSTS ============
    cost_post_create_non_campaign = models.PositiveIntegerField(
        default=0, help_text='Cost to create a non-campaign post (0 = free)'
    )
    cost_like_non_campaign = models.PositiveIntegerField(
        default=0, help_text='Coins charged when liking a non-campaign post (0 = free)'
    )
    cost_comment_non_campaign = models.PositiveIntegerField(
        default=0, help_text='Coins charged when commenting on a non-campaign post (0 = free)'
    )
    cost_share_non_campaign = models.PositiveIntegerField(
        default=0, help_text='Coins charged when sharing a non-campaign post (0 = free)'
    )
    cost_gift_non_campaign = models.PositiveIntegerField(
        default=0,
        help_text='Extra coins charged on top of gift value when gifting on a non-campaign post (0 = free)',
    )
    cost_boost_1hr_non_campaign = models.PositiveIntegerField(
        default=100, help_text='Cost to boost non-campaign post for 1 hour'
    )
    cost_boost_2hr_non_campaign = models.PositiveIntegerField(default=200)
    cost_boost_24hr_non_campaign = models.PositiveIntegerField(default=800)
    cost_trending_1hr_non_campaign = models.PositiveIntegerField(
        default=150, help_text='Cost to make non-campaign post trending for 1 hour'
    )
    cost_trending_24hr_non_campaign = models.PositiveIntegerField(
        default=1200, help_text='Cost to make non-campaign post trending for 24 hours'
    )
    cost_post_create_long_video_non_campaign = models.PositiveIntegerField(
        default=0, help_text='Additional coins for non-campaign videos > 60 seconds (0 = free)'
    )

    # ============ MINIMUM BALANCE THRESHOLDS ============
    min_balance_to_post = models.PositiveIntegerField(default=0)
    min_balance_to_join_campaign = models.PositiveIntegerField(default=50)

    # ============ WITHDRAWAL (Coin -> Birr) ============
    withdrawal_enabled = models.BooleanField(
        default=True, help_text='Allow users to withdraw coins to Birr'
    )
    withdrawal_min_coins = models.PositiveIntegerField(
        default=1000, help_text='Minimum coins required to withdraw'
    )
    withdrawal_max_coins_per_request = models.PositiveIntegerField(default=100000)
    coins_per_birr = models.PositiveIntegerField(
        default=100, help_text='How many coins = 1 ETB (e.g. 100 means 100 coins -> 1 ETB)'
    )
    withdrawal_fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.00'),
        help_text='Service fee % on withdrawal',
    )
    withdrawal_processing_days = models.PositiveIntegerField(
        default=3, help_text='Days to process withdrawal'
    )

    # ============ POINTS SYSTEM (Points -> Birr only) ============
    # Points are separate from coins and can only be withdrawn/transferred as birr
    coins_to_points_conversion = models.PositiveIntegerField(
        default=1, help_text='How many coins = 1 point (gift conversion)'
    )
    points_per_birr = models.PositiveIntegerField(
        default=10, help_text='How many points = 1 ETB (withdrawal)'
    )
    withdrawal_min_points = models.PositiveIntegerField(
        default=1000, help_text='Minimum points required to withdraw'
    )
    withdrawal_max_points_per_request = models.PositiveIntegerField(
        default=50000, help_text='Maximum points that can be withdrawn per request'
    )

    # ============ CAMPAIGN WINNER POINT REWARDS ============
    daily_winner_points = models.PositiveIntegerField(
        default=500, help_text='Points awarded to daily campaign winners'
    )
    weekly_winner_points = models.PositiveIntegerField(
        default=2000, help_text='Points awarded to weekly campaign winners'
    )
    monthly_winner_points = models.PositiveIntegerField(
        default=10000, help_text='Points awarded to monthly campaign winners'
    )
    grand_finalist_points = models.PositiveIntegerField(
        default=5000, help_text='Points awarded to grand campaign finalists'
    )
    grand_winner_points = models.PositiveIntegerField(
        default=50000, help_text='Points awarded to grand campaign winners'
    )

    # ============ GIFTING POLICY ============
    earned_coins_giftable = models.BooleanField(
        default=False, help_text='Can earned coins be sent as gifts?'
    )
    purchased_coins_giftable = models.BooleanField(default=True)
    earned_coins_withdrawable = models.BooleanField(
        default=True, help_text='Can earned coins be withdrawn to Birr?'
    )
    purchased_coins_withdrawable = models.BooleanField(
        default=False, help_text='Should not allow purchased->Birr (money laundering)'
    )

    # ============ GIFT RESTRICTIONS (Point Transfer Rules) ============
    gift_min_points_per_transaction = models.PositiveIntegerField(
        default=10, help_text='Minimum points per gift transaction'
    )
    gift_max_points_per_transaction = models.PositiveIntegerField(
        default=5000, help_text='Maximum points per single gift'
    )
    gift_max_points_to_recipient_per_day = models.PositiveIntegerField(
        default=5000, help_text='Max points to one recipient per day (Voting Cap)'
    )
    gift_max_total_points_sent_per_day = models.PositiveIntegerField(
        default=10000, help_text='Max total points sent per user per day'
    )

    # ============ EXPIRY ============
    earned_coins_expire_days = models.PositiveIntegerField(default=0, help_text='0 = never expire')

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='wallet_config_updates'
    )

    class Meta:
        verbose_name = 'Wallet Configuration'
        verbose_name_plural = 'Wallet Configuration'

    def __str__(self):
        return f'Wallet Config (updated {self.updated_at:%Y-%m-%d %H:%M})'

    def save(self, *args, **kwargs):
        # Force singleton: always id=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        """Get or create the singleton config"""
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    def coins_to_birr(self, coins):
        """Convert coin amount to ETB"""
        if self.coins_per_birr <= 0:
            return Decimal('0')
        return Decimal(coins) / Decimal(self.coins_per_birr)

    def points_to_birr(self, points):
        """Convert point amount to ETB"""
        if self.points_per_birr <= 0:
            return Decimal('0')
        return Decimal(points) / Decimal(self.points_per_birr)

    def coins_to_points(self, coins):
        """Convert coins to points (for gift conversion)"""
        if self.coins_to_points_conversion <= 0:
            return 0
        return coins // self.coins_to_points_conversion

    def calculate_withdrawal(self, coins):
        """Calculate net Birr after fees for a coin withdrawal"""
        gross_birr = self.coins_to_birr(coins)
        fee = gross_birr * (self.withdrawal_fee_percent / Decimal('100'))
        net_birr = gross_birr - fee
        return {
            'coins': coins,
            'gross_birr': gross_birr,
            'fee_birr': fee,
            'net_birr': net_birr,
            'fee_percent': self.withdrawal_fee_percent,
        }

    def calculate_points_withdrawal(self, points):
        """Calculate net Birr after fees for a points withdrawal"""
        gross_birr = self.points_to_birr(points)
        fee = gross_birr * (self.withdrawal_fee_percent / Decimal('100'))
        net_birr = gross_birr - fee
        return {
            'points': points,
            'gross_birr': gross_birr,
            'fee_birr': fee,
            'net_birr': net_birr,
            'fee_percent': self.withdrawal_fee_percent,
        }


class WithdrawalRequest(models.Model):
    """
    User requests to convert their earned coins to Ethiopian Birr.
    Admin reviews and approves/rejects.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('processing', 'Processing Payout'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled by User'),
    ]

    PAYOUT_METHODS = [
        ('telebirr', 'Telebirr'),
        ('bank_transfer', 'Bank Transfer'),
        ('cbe_birr', 'CBE Birr'),
        ('mpesa', 'M-Pesa Ethiopia'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawal_requests')

    # Amounts (supports both coins and points)
    coin_amount = models.PositiveIntegerField(
        default=0, help_text='Coins to convert (legacy, use point_amount instead)'
    )
    point_amount = models.PositiveIntegerField(default=0, help_text='Points to convert to birr')
    gross_birr = models.DecimalField(max_digits=12, decimal_places=2)
    fee_birr = models.DecimalField(max_digits=12, decimal_places=2)
    net_birr = models.DecimalField(
        max_digits=12, decimal_places=2, help_text='Final amount sent to user'
    )
    conversion_rate = models.PositiveIntegerField(
        help_text='Coins/Points per Birr at time of request'
    )

    # Payout details
    payout_method = models.CharField(max_length=20, choices=PAYOUT_METHODS, default='telebirr')
    payout_account = models.CharField(max_length=100, help_text='Phone number or bank account')
    payout_account_name = models.CharField(
        max_length=200, blank=True, help_text='Account holder name'
    )

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    payout_reference = models.CharField(
        max_length=100, blank=True, help_text='Telebirr/bank reference number'
    )

    # B2C transaction fields (for Telebirr automatic payouts)
    b2c_transaction_id = models.UUIDField(
        null=True, blank=True, help_text='Linked B2CPaymentTransaction ID'
    )
    originator_conversation_id = models.CharField(
        max_length=100, blank=True, help_text='B2C originator conversation ID'
    )
    conversation_id = models.CharField(
        max_length=100, blank=True, help_text='B2C conversation ID from Telebirr'
    )
    telebirr_transaction_id = models.CharField(
        max_length=100, blank=True, help_text='Telebirr transaction ID'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_withdrawals'
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['originator_conversation_id']),
        ]

    def __str__(self):
        return (
            f'{self.user.username}: {self.coin_amount} coins -> {self.net_birr} ETB ({self.status})'
        )

    def can_cancel(self):
        return self.status == 'pending'

    def mark_completed(self, admin_user, payout_reference=''):
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.reviewed_by = admin_user
        if payout_reference:
            self.payout_reference = payout_reference
        self.save()

    def refund_to_user(self, *, reason):
        """Put back what this withdrawal took. Returns what went back.

        A withdrawal takes the balance when it is *requested* -- see
        `api/views/wallet.py::request_withdrawal`, "Deduct points now
        (refunded if rejected)" -- so every ending that does not pay the user
        has to give it back: admin rejection, cancellation by the user, or a
        payout that could not be started.

        One method for all of them because a withdrawal row can carry either
        kind of balance. `point_amount` is the current flow; `coin_amount` is
        the legacy one and is zero on anything created since. Refunding the
        wrong one is how this went wrong before: rejection refunded
        `coin_amount` alone, which a points withdrawal never sets, so the
        refund ran, reported success and moved nothing -- the user's points
        were gone for good.

        Both paths here row-lock the balance they touch (`add_points` and
        `add_earned` do it internally), so a refund racing another change to
        the same balance cannot lose an update.

        `points_withdrawn_total` is deliberately not wound back: it is a
        lifetime counter that only ever goes up, and the automatic payout
        path made the same choice for the same reason. It therefore counts
        some withdrawals that were never paid -- inaccurate, but only in a
        reported total, and it is not this method's to change alone.

        **The caller is responsible for not calling this twice.** There is no
        flag on the row saying a refund happened; what prevents a double
        refund is the caller holding the withdrawal's row lock and moving it
        out of a refundable status in the same transaction. Every call site
        here does that.
        """
        refunded = {'points': 0, 'coins': 0}

        if self.point_amount:
            profile = self.user.profile
            # total_field is omitted on purpose: see the note above.
            profile.add_points(self.point_amount, total_field=None)
            refunded['points'] = self.point_amount

        if self.coin_amount:
            from .contest import UserCoinBalance

            balance, _ = UserCoinBalance.objects.get_or_create(user=self.user)
            balance.add_earned(
                self.coin_amount,
                transaction_type='refund',
                description=f'Refund for {reason} withdrawal #{self.pk}',
            )
            refunded['coins'] = self.coin_amount

        return refunded

    def mark_rejected(self, admin_user, reason=''):
        """Reject this withdrawal and return the balance it took.

        Call inside a transaction holding this row's lock, having checked the
        status: that is what stops a second rejection refunding twice.
        """
        self.status = 'rejected'
        self.reviewed_at = timezone.now()
        self.reviewed_by = admin_user
        self.rejection_reason = reason
        self.save()

        return self.refund_to_user(reason='rejected')
