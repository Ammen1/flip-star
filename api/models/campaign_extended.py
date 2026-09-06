from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from .campaign import Campaign


class CampaignScoringConfig(models.Model):
    """Configurable scoring weights for campaigns - supports Daily, Weekly, Monthly, Grand types

    The four engagement weights default to the platform formula:

        score = likes x 1 + comments x 2 + shares x 5 + gifts x 10

    Shares and gifts previously defaulted to 3 and 5. Nothing observed the
    difference, because both call sites hardcoded the share count to zero and
    the weight multiplied nothing -- see api/services/scoring/leaderboard.py,
    which is now the single implementation of the formula above.

    These stay per-campaign and per-type: a campaign may weight its own
    engagement differently, and the defaults are only what it starts from.
    """

    campaign = models.OneToOneField(
        Campaign, on_delete=models.CASCADE, related_name='scoring_config'
    )

    # ============================================================================
    # DAILY CAMPAIGN SETTINGS
    # ============================================================================
    # Winner selection split
    daily_top_scorer_percentage = models.IntegerField(
        default=70, help_text='Percentage of winners from top scorers (Daily)'
    )
    daily_random_percentage = models.IntegerField(
        default=30, help_text='Percentage of winners from random participants (Daily)'
    )

    # Engagement weights for daily
    daily_likes_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.0, help_text='Points per like (Daily)'
    )
    daily_comments_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.0, help_text='Points per comment (Daily)'
    )
    daily_shares_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.0, help_text='Points per share (Daily)'
    )
    daily_gifts_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.0,
        help_text='Points per unique gifter on a post (Daily)',
    )

    # Gamification weights for daily
    daily_spin_reward_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.0, help_text='Points for daily spin reward'
    )
    daily_coin_gift_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.0, help_text='Points per coin gift received'
    )
    daily_login_bonus_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=3.0, help_text='Points for daily login bonus'
    )

    # Daily consistency
    daily_post_points = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.0, help_text='Points for posting that day'
    )

    # Daily win limit (days)
    daily_win_cooldown_days = models.IntegerField(
        default=7, help_text='Days before user can win again (Daily)'
    )

    # Frequency caps read by WinnerFrequencyRecord.check_frequency_eligibility
    # (below) -- how many times a user may win each tier within its period,
    # independent of daily_win_cooldown_days above (a spacing rule, not a cap).
    daily_win_limit_per_month = models.IntegerField(
        default=1, help_text='Max daily wins per month per user'
    )
    weekly_win_limit_per_month = models.IntegerField(
        default=1, help_text='Max weekly wins per month per user'
    )
    monthly_win_limit_per_period = models.IntegerField(
        default=1, help_text='Max monthly wins per campaign period per user'
    )
    grand_win_limit_per_campaign = models.IntegerField(
        default=1, help_text='Max grand wins per campaign per user'
    )

    # ============================================================================
    # WEEKLY CAMPAIGN SETTINGS
    # ============================================================================
    # Engagement weights for weekly
    weekly_likes_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.0, help_text='Points per like (Weekly)'
    )
    weekly_comments_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.0, help_text='Points per comment (Weekly)'
    )
    weekly_shares_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.0, help_text='Points per share (Weekly)'
    )
    weekly_gifts_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.0,
        help_text='Points per unique gifter on a post (Weekly)',
    )

    # Gamification weights for weekly
    weekly_spin_reward_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=3.0, help_text='Points for spin reward (Weekly)'
    )
    weekly_coin_gift_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.5, help_text='Points per coin gift (Weekly)'
    )
    weekly_consistency_boost = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.0, help_text='Points per day participated'
    )

    # Streak bonuses for weekly
    weekly_streak_3day_bonus = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.0, help_text='Bonus for 3-day streak'
    )
    weekly_streak_5day_bonus = models.DecimalField(
        max_digits=5, decimal_places=2, default=25.0, help_text='Bonus for 5-day streak'
    )
    weekly_streak_7day_bonus = models.DecimalField(
        max_digits=5, decimal_places=2, default=50.0, help_text='Bonus for 7-day streak (full week)'
    )

    # Decay settings
    weekly_decay_per_missed_day = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.0, help_text='Points deducted per missed day'
    )
    weekly_decay_max_days = models.IntegerField(
        default=3, help_text='Max days for decay calculation'
    )

    # ============================================================================
    # MONTHLY CAMPAIGN SETTINGS
    # ============================================================================
    # Engagement weights for monthly
    monthly_likes_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.0, help_text='Points per like (Monthly)'
    )
    monthly_comments_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.0, help_text='Points per comment (Monthly)'
    )
    monthly_shares_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.0, help_text='Points per share (Monthly)'
    )
    monthly_gifts_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.0,
        help_text='Points per unique gifter on a post (Monthly)',
    )

    # Gamification weights for monthly
    monthly_spin_reward_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.0, help_text='Points for spin reward (Monthly)'
    )
    monthly_coin_gift_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.0, help_text='Points per coin gift (Monthly)'
    )
    monthly_consistency_multiplier = models.DecimalField(
        max_digits=3, decimal_places=2, default=1.5, help_text='Multiplier for consistent posting'
    )

    # Weekly winner bonus (for monthly campaigns)
    monthly_weekly_winner_bonus = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20.0,
        help_text='Bonus points for weekly campaign winners',
    )

    # Streak multipliers for monthly
    monthly_streak_7day_multiplier = models.DecimalField(
        max_digits=3, decimal_places=2, default=1.2, help_text='Multiplier for 7-day streak'
    )
    monthly_streak_14day_multiplier = models.DecimalField(
        max_digits=3, decimal_places=2, default=1.5, help_text='Multiplier for 14-day streak'
    )
    monthly_streak_21day_multiplier = models.DecimalField(
        max_digits=3, decimal_places=2, default=2.0, help_text='Multiplier for 21-day streak'
    )

    # High engagement bonus
    monthly_high_engagement_threshold = models.IntegerField(
        default=100, help_text='Likes threshold for high engagement'
    )
    monthly_high_engagement_bonus = models.DecimalField(
        max_digits=5, decimal_places=2, default=15.0, help_text='Bonus for high engagement posts'
    )

    # ============================================================================
    # GRAND CAMPAIGN SETTINGS
    # ============================================================================
    # Phase 1: Qualification (similar to monthly)
    grand_qualification_likes_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.0, help_text='Points per like (Qualification)'
    )
    grand_qualification_comments_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=2.0, help_text='Points per comment (Qualification)'
    )
    grand_qualification_shares_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.0, help_text='Points per share (Qualification)'
    )
    grand_qualification_gifts_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10.0,
        help_text='Points per unique gifter on a post (Qualification)',
    )

    # Phase 2: Final Judging
    grand_judging_weight = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0.70,
        help_text='Weight for judge/admin scoring (0.0-1.0)',
    )
    grand_voting_weight = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.30, help_text='Weight for public voting (0.0-1.0)'
    )

    # Judge scoring criteria
    grand_judge_creativity_max = models.DecimalField(
        max_digits=5, decimal_places=2, default=30.0, help_text='Max creativity points from judges'
    )
    grand_judge_quality_max = models.DecimalField(
        max_digits=5, decimal_places=2, default=25.0, help_text='Max quality points from judges'
    )
    grand_judge_theme_max = models.DecimalField(
        max_digits=5, decimal_places=2, default=20.0, help_text='Max theme relevance from judges'
    )
    grand_judge_impact_max = models.DecimalField(
        max_digits=5, decimal_places=2, default=25.0, help_text='Max impact points from judges'
    )

    # Voting settings
    grand_max_votes_per_user = models.IntegerField(
        default=3, help_text='Max finalists a user can vote for'
    )
    grand_vote_value = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.0, help_text='Points per vote received'
    )

    # Qualification threshold (top X% move to finals)
    grand_qualification_percentage = models.IntegerField(
        default=20, help_text='Top percentage that qualifies for finals'
    )

    # ============================================================================
    # LEGACY/COMPATIBILITY FIELDS (kept for existing functionality)
    # ============================================================================
    # Maximum points for each component (configurable by admin)
    max_creativity_points = models.DecimalField(
        max_digits=5, decimal_places=2, default=30, help_text='Max points for creativity'
    )
    max_engagement_points = models.DecimalField(
        max_digits=5, decimal_places=2, default=25, help_text='Max points for engagement'
    )
    max_consistency_points = models.DecimalField(
        max_digits=5, decimal_places=2, default=20, help_text='Max points for consistency'
    )
    max_quality_points = models.DecimalField(
        max_digits=5, decimal_places=2, default=15, help_text='Max points for quality'
    )
    max_theme_relevance_points = models.DecimalField(
        max_digits=5, decimal_places=2, default=10, help_text='Max points for theme relevance'
    )

    # Engagement calculation weights (legacy)
    likes_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.6,
        help_text='Weight for likes in engagement score',
    )
    comments_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1.5,
        help_text='Weight for comments in engagement score',
    )
    shares_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2.0,
        help_text='Weight for shares in engagement score',
    )

    # Consistency calculation settings (legacy)
    streak_points_per_day = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.0, help_text='Points per day of streak'
    )
    participation_points_per_day = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.5, help_text='Points per day participated'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Campaign Scoring Configuration'
        verbose_name_plural = 'Campaign Scoring Configurations'

    def __str__(self):
        return f'Scoring Config for {self.campaign.title} ({self.campaign.campaign_type})'

    def get_config_for_type(self, campaign_type=None):
        """Get scoring configuration dictionary for a specific campaign type"""
        if campaign_type is None:
            campaign_type = self.campaign.campaign_type

        configs = {
            'daily': {
                'type': 'daily',
                'engagement': {
                    'likes_weight': float(self.daily_likes_weight),
                    'comments_weight': float(self.daily_comments_weight),
                    'shares_weight': float(self.daily_shares_weight),
                    'gifts_weight': float(self.daily_gifts_weight),
                },
                'gamification': {
                    'spin_reward': float(self.daily_spin_reward_weight),
                    'coin_gift': float(self.daily_coin_gift_weight),
                    'login_bonus': float(self.daily_login_bonus_weight),
                },
                'consistency': {
                    'daily_post_points': float(self.daily_post_points),
                },
                'winner_selection': {
                    'top_percentage': self.daily_top_scorer_percentage,
                    'random_percentage': self.daily_random_percentage,
                },
                'win_cooldown_days': self.daily_win_cooldown_days,
            },
            'weekly': {
                'type': 'weekly',
                'engagement': {
                    'likes_weight': float(self.weekly_likes_weight),
                    'comments_weight': float(self.weekly_comments_weight),
                    'shares_weight': float(self.weekly_shares_weight),
                    'gifts_weight': float(self.weekly_gifts_weight),
                },
                'gamification': {
                    'spin_reward': float(self.weekly_spin_reward_weight),
                    'coin_gift': float(self.weekly_coin_gift_weight),
                    'consistency_boost': float(self.weekly_consistency_boost),
                },
                'streak_bonuses': {
                    '3_day': float(self.weekly_streak_3day_bonus),
                    '5_day': float(self.weekly_streak_5day_bonus),
                    '7_day': float(self.weekly_streak_7day_bonus),
                },
                'decay': {
                    'per_missed_day': float(self.weekly_decay_per_missed_day),
                    'max_days': self.weekly_decay_max_days,
                },
            },
            'monthly': {
                'type': 'monthly',
                'engagement': {
                    'likes_weight': float(self.monthly_likes_weight),
                    'comments_weight': float(self.monthly_comments_weight),
                    'shares_weight': float(self.monthly_shares_weight),
                    'gifts_weight': float(self.monthly_gifts_weight),
                },
                'gamification': {
                    'spin_reward': float(self.monthly_spin_reward_weight),
                    'coin_gift': float(self.monthly_coin_gift_weight),
                    'consistency_multiplier': float(self.monthly_consistency_multiplier),
                },
                'weekly_winner_bonus': float(self.monthly_weekly_winner_bonus),
                'streak_multipliers': {
                    '7_day': float(self.monthly_streak_7day_multiplier),
                    '14_day': float(self.monthly_streak_14day_multiplier),
                    '21_day': float(self.monthly_streak_21day_multiplier),
                },
                'high_engagement': {
                    'threshold': self.monthly_high_engagement_threshold,
                    'bonus': float(self.monthly_high_engagement_bonus),
                },
            },
            'grand': {
                'type': 'grand',
                'phase1_qualification': {
                    'likes_weight': float(self.grand_qualification_likes_weight),
                    'comments_weight': float(self.grand_qualification_comments_weight),
                    'shares_weight': float(self.grand_qualification_shares_weight),
                    'gifts_weight': float(self.grand_qualification_gifts_weight),
                    'qualification_percentage': self.grand_qualification_percentage,
                },
                'phase2_judging': {
                    'judging_weight': float(self.grand_judging_weight),
                    'voting_weight': float(self.grand_voting_weight),
                    'judge_criteria': {
                        'creativity_max': float(self.grand_judge_creativity_max),
                        'quality_max': float(self.grand_judge_quality_max),
                        'theme_max': float(self.grand_judge_theme_max),
                        'impact_max': float(self.grand_judge_impact_max),
                    },
                    'voting': {
                        'max_votes_per_user': self.grand_max_votes_per_user,
                        'vote_value': float(self.grand_vote_value),
                    },
                },
            },
        }

        return configs.get(campaign_type, configs['daily'])


class CampaignTheme(models.Model):
    """Weekly themes for campaigns"""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='themes')
    title = models.CharField(max_length=200)
    description = models.TextField()
    week_number = models.IntegerField(help_text='Week 1, 2, 3, etc.')

    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    hashtags = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['campaign', 'week_number']
        unique_together = ['campaign', 'week_number']

    def __str__(self):
        return f'{self.campaign.title} - Week {self.week_number}: {self.title}'

    def activate(self):
        """Activate this theme and deactivate others in the same campaign"""
        CampaignTheme.objects.filter(campaign=self.campaign).update(is_active=False)
        self.is_active = True
        self.save()


class PostScore(models.Model):
    """Scoring for campaign posts"""

    MODERATION_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    reel = models.OneToOneField('api.Reel', on_delete=models.CASCADE, related_name='campaign_score')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='post_scores')
    theme = models.ForeignKey(
        CampaignTheme, on_delete=models.SET_NULL, null=True, blank=True, related_name='post_scores'
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='campaign_scores')

    # Moderation
    moderation_status = models.CharField(
        max_length=20, choices=MODERATION_STATUS, default='pending'
    )
    rejection_reason = models.TextField(blank=True)
    moderated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderated_posts'
    )
    moderated_at = models.DateTimeField(null=True, blank=True)

    # Score components (out of 100 total)
    creativity_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, help_text='Max 30 points'
    )
    engagement_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, help_text='Max 25 points'
    )
    consistency_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, help_text='Max 20 points'
    )
    quality_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, help_text='Max 15 points'
    )
    theme_relevance_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, help_text='Max 10 points'
    )

    # Total score
    total_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-total_score', '-created_at']
        indexes = [
            models.Index(fields=['campaign', '-total_score']),
            models.Index(fields=['user', 'campaign']),
        ]

    def __str__(self):
        return f'Score for {self.user.username} - {self.total_score}'

    def calculate_total_score(self):
        """Calculate and update total score"""
        self.total_score = (
            self.creativity_score
            + self.engagement_score
            + self.consistency_score
            + self.quality_score
            + self.theme_relevance_score
        )
        self.save()
        return self.total_score

    def update_engagement_score(self):
        """Calculate engagement score based on likes, comments, shares using configurable weights"""
        from .core import Comment, Vote

        # Get scoring config for this campaign
        config, _ = CampaignScoringConfig.objects.get_or_create(campaign=self.campaign)

        likes = Vote.objects.filter(reel=self.reel).count()
        comments = Comment.objects.filter(reel=self.reel).count()
        # shares = 0  # TODO: Implement shares tracking

        # Use configurable weights
        raw_engagement = (likes * float(config.likes_weight)) + (
            comments * float(config.comments_weight)
        )

        # Normalize to max points configured by admin
        max_points = float(config.max_engagement_points)
        self.engagement_score = min(max_points, raw_engagement / 10)  # Scale down
        self.save()
        self.calculate_total_score()


class UserCampaignStats(models.Model):
    """Aggregated stats for user participation in a campaign"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='campaign_stats')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='user_stats')

    # Participation metrics
    total_posts = models.IntegerField(default=0)
    approved_posts = models.IntegerField(default=0)
    rejected_posts = models.IntegerField(default=0)

    # Scoring
    total_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    average_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Consistency tracking
    days_participated = models.IntegerField(default=0)
    current_streak = models.IntegerField(default=0)
    longest_streak = models.IntegerField(default=0)
    last_post_date = models.DateField(null=True, blank=True)

    # Rankings
    daily_rank = models.IntegerField(null=True, blank=True)
    weekly_rank = models.IntegerField(null=True, blank=True)
    monthly_rank = models.IntegerField(null=True, blank=True)
    overall_rank = models.IntegerField(null=True, blank=True)

    # State tracking
    has_won_current_cycle = models.BooleanField(
        default=False, help_text='True if user has won in the current active period (week/month)'
    )
    last_win_date = models.DateTimeField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'campaign']
        ordering = ['-total_score']
        indexes = [
            models.Index(fields=['campaign', '-total_score']),
        ]

    def __str__(self):
        return f'{self.user.username} - {self.campaign.title} ({self.total_score})'

    def update_stats(self):
        """Recalculate all stats for this user in this campaign"""
        scores = PostScore.objects.filter(
            user=self.user, campaign=self.campaign, moderation_status='approved'
        )

        self.approved_posts = scores.count()
        self.total_score = sum(score.total_score for score in scores)
        self.average_score = (
            self.total_score / self.approved_posts if self.approved_posts > 0 else 0
        )

        # Update rejected posts
        self.rejected_posts = PostScore.objects.filter(
            user=self.user, campaign=self.campaign, moderation_status='rejected'
        ).count()

        self.total_posts = self.approved_posts + self.rejected_posts

        # Streak calculation based on campaign type
        config, _ = CampaignScoringConfig.objects.get_or_create(campaign=self.campaign)

        # Add consistency score based on streak
        self.total_score += self.current_streak * config.streak_points_per_day
        self.total_score += self.days_participated * config.participation_points_per_day

        self.save()


class Leaderboard(models.Model):
    """Leaderboard snapshots for different time periods"""

    PERIOD_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('overall', 'Overall'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='leaderboards')
    period_type = models.CharField(max_length=20, choices=PERIOD_CHOICES)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    is_current = models.BooleanField(default=True)
    is_finalized = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period_start']
        indexes = [
            models.Index(fields=['campaign', 'period_type', '-period_start']),
        ]

    def __str__(self):
        return f'{self.campaign.title} - {self.period_type} ({self.period_start.date()})'


class LeaderboardEntry(models.Model):
    """Individual entries in a leaderboard"""

    leaderboard = models.ForeignKey(Leaderboard, on_delete=models.CASCADE, related_name='entries')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='leaderboard_entries')

    rank = models.IntegerField()
    score = models.DecimalField(max_digits=10, decimal_places=2)
    posts_count = models.IntegerField(default=0)

    # Bonus points
    bonus_points = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['rank']
        unique_together = ['leaderboard', 'user']
        indexes = [
            models.Index(fields=['leaderboard', 'rank']),
        ]

    def __str__(self):
        return f'#{self.rank} {self.user.username} - {self.score}'


class WinnerSelection(models.Model):
    """Track winner selection for different periods"""

    SELECTION_TYPE = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('grand', 'Grand Finale'),
    ]

    campaign = models.ForeignKey(
        Campaign, on_delete=models.CASCADE, related_name='winner_selections'
    )
    selection_type = models.CharField(max_length=20, choices=SELECTION_TYPE)
    leaderboard = models.ForeignKey(
        Leaderboard, on_delete=models.CASCADE, related_name='winner_selections'
    )

    # Selection criteria
    top_scorers_percentage = models.IntegerField(
        default=70, help_text='Percentage from top scorers'
    )
    random_participants_percentage = models.IntegerField(
        default=30, help_text='Percentage from random active users'
    )

    is_finalized = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='finalized_selections'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.campaign.title} - {self.selection_type} winners'


class SelectedWinner(models.Model):
    """Individual winners from selection process"""

    selection = models.ForeignKey(WinnerSelection, on_delete=models.CASCADE, related_name='winners')
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='campaign_winner_selections'
    )

    rank = models.IntegerField()
    final_score = models.DecimalField(max_digits=10, decimal_places=2)
    selection_method = models.CharField(
        max_length=20, choices=[('top_scorer', 'Top Scorer'), ('random', 'Random Selection')]
    )

    prize_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    prize_claimed = models.BooleanField(default=False)
    prize_claimed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['rank']
        unique_together = ['selection', 'rank']

    def __str__(self):
        return f'#{self.rank} {self.user.username} - {self.selection.selection_type}'


class CampaignBadge(models.Model):
    """Badges earned by users in campaigns"""

    BADGE_TYPES = [
        ('participation', 'Participation'),
        ('consistency', 'Consistency'),
        ('top_scorer', 'Top Scorer'),
        ('winner', 'Winner'),
        ('engagement_king', 'Engagement King'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='campaign_badges')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='badges')
    badge_type = models.CharField(max_length=50, choices=BADGE_TYPES)

    title = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=50, blank=True, help_text='Emoji or icon identifier')

    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-earned_at']

    def __str__(self):
        return f'{self.user.username} - {self.title}'


class GamificationActivity(models.Model):
    """Track gamification activities for scoring (spins, coin gifts, login bonuses)"""

    ACTIVITY_TYPES = [
        ('spin_reward', 'Daily Spin Reward'),
        ('coin_gift_received', 'Coin Gift Received'),
        ('coin_gift_sent', 'Coin Gift Sent'),
        ('login_bonus', 'Daily Login Bonus'),
        ('streak_bonus', 'Streak Bonus'),
        ('referral_bonus', 'Referral Bonus'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gamification_activities')
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='gamification_activities',
        null=True,
        blank=True,
    )

    activity_type = models.CharField(max_length=30, choices=ACTIVITY_TYPES)
    points_value = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, help_text='Points earned for this activity'
    )

    # Context data
    metadata = models.JSONField(
        default=dict, blank=True, help_text='Additional context (e.g., spin result, gift sender)'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    activity_date = models.DateField(help_text='The date this activity counts for')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'campaign', 'activity_date']),
            models.Index(fields=['user', 'activity_type', 'activity_date']),
        ]

    def __str__(self):
        return f'{self.user.username} - {self.activity_type} ({self.points_value} pts)'


class JudgeScore(models.Model):
    """Judge/admin scoring for Grand Campaign finalists (Phase 2)"""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='judge_scores')
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='judge_scores',
        help_text='User being judged (the finalist)',
    )
    judge = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='scores_given',
        help_text='Judge who gave the score',
    )

    # Judge criteria scores
    creativity_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    quality_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    theme_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    impact_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Comments/feedback
    judge_comments = models.TextField(blank=True, help_text='Judge feedback/comments')

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['campaign', 'user', 'judge']
        ordering = ['-created_at']

    def __str__(self):
        return f'Judge {self.judge.username} scored {self.user.username} - {self.campaign.title}'

    @property
    def total_score(self):
        return self.creativity_score + self.quality_score + self.theme_score + self.impact_score


class PublicVote(models.Model):
    """Public voting for Grand Campaign finalists (Phase 2)"""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='public_votes')
    voter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='campaign_votes_cast')
    finalist = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='campaign_votes_received',
        help_text='User being voted for',
    )

    # Vote value (can be weighted)
    vote_value = models.DecimalField(max_digits=5, decimal_places=2, default=1)

    # Optional: IP tracking for fraud prevention
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['campaign', 'voter', 'finalist']
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['campaign', 'finalist']),
            models.Index(fields=['campaign', 'voter']),
        ]

    def __str__(self):
        return f'{self.voter.username} voted for {self.finalist.username} in {self.campaign.title}'


class GrandFinalist(models.Model):
    """Track users who qualified for Grand Campaign finals (Phase 2)"""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='finalists')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='grand_finals')

    # Qualification data
    qualification_score = models.DecimalField(max_digits=10, decimal_places=2)
    qualification_rank = models.IntegerField()

    # Phase 2 scores
    judge_score_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vote_count = models.IntegerField(default=0)
    vote_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    final_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Status
    is_finalist = models.BooleanField(default=True)
    final_rank = models.IntegerField(null=True, blank=True)
    is_winner = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['campaign', 'user']
        ordering = ['qualification_rank']

    def __str__(self):
        return f'Finalist #{self.qualification_rank}: {self.user.username} - {self.campaign.title}'


class WinnerFrequencyRecord(models.Model):
    """Track when users win to enforce frequency restrictions"""

    WINNER_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('grand', 'Grand'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='winner_frequency_records'
    )
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='winner_frequency_records',
        null=True,
        blank=True,
    )

    winner_type = models.CharField(max_length=20, choices=WINNER_TYPE_CHOICES)
    won_at = models.DateTimeField(auto_now_add=True)

    period_start = models.DateTimeField(help_text='Start of the period this win belongs to')
    period_end = models.DateTimeField(help_text='End of the period this win belongs to')

    selection = models.ForeignKey(
        WinnerSelection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='frequency_records',
    )

    class Meta:
        unique_together = ['user', 'winner_type', 'period_start']
        indexes = [
            models.Index(fields=['user', 'winner_type', '-won_at']),
            models.Index(fields=['winner_type', 'period_start', 'period_end']),
        ]
        ordering = ['-won_at']

    def __str__(self):
        campaign_name = self.campaign.title if self.campaign else 'General'
        return f'{self.user.username} - {self.winner_type} winner ({campaign_name}) - {self.won_at.date()}'

    @classmethod
    def check_frequency_eligibility(cls, user, winner_type, campaign=None):
        """Check if user is eligible to win based on frequency restrictions.

        Returns (is_eligible, current_wins, limit).
        """
        now = timezone.now()

        config = None
        if campaign:
            config = CampaignScoringConfig.objects.filter(campaign=campaign).first()

        if winner_type == 'daily':
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_end = (month_start + timedelta(days=32)).replace(day=1)

            recent_wins = cls.objects.filter(
                user=user,
                winner_type='daily',
                won_at__gte=month_start,
                won_at__lt=month_end,
            ).count()

            limit = config.daily_win_limit_per_month if config else 1
            return recent_wins < limit, recent_wins, limit

        elif winner_type == 'weekly':
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_end = (month_start + timedelta(days=32)).replace(day=1)

            recent_wins = cls.objects.filter(
                user=user,
                winner_type='weekly',
                won_at__gte=month_start,
                won_at__lt=month_end,
            ).count()

            limit = config.weekly_win_limit_per_month if config else 1
            return recent_wins < limit, recent_wins, limit

        elif winner_type == 'monthly':
            if campaign:
                recent_wins = cls.objects.filter(
                    user=user, winner_type='monthly', campaign=campaign
                ).count()
            else:
                recent_wins = cls.objects.filter(user=user, winner_type='monthly').count()

            limit = config.monthly_win_limit_per_period if config else 1
            return recent_wins < limit, recent_wins, limit

        elif winner_type == 'grand':
            if campaign:
                recent_wins = cls.objects.filter(
                    user=user, winner_type='grand', campaign=campaign
                ).count()
            else:
                recent_wins = cls.objects.filter(user=user, winner_type='grand').count()

            limit = config.grand_win_limit_per_campaign if config else 1
            return recent_wins < limit, recent_wins, limit

        return True, 0, 1

    @classmethod
    def record_win(
        cls, user, winner_type, campaign=None, selection=None, period_start=None, period_end=None
    ):
        """Record a win for frequency tracking. Returns (record, created)."""
        now = timezone.now()

        if period_start is None:
            if winner_type == 'daily':
                period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                period_end = period_start + timedelta(days=1)
            elif winner_type == 'weekly':
                period_start = now - timedelta(days=now.weekday())
                period_start = period_start.replace(hour=0, minute=0, second=0, microsecond=0)
                period_end = period_start + timedelta(days=7)
            elif winner_type == 'monthly':
                period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                next_month = period_start + timedelta(days=32)
                period_end = next_month.replace(day=1)
            elif winner_type == 'grand':
                period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                period_end = now + timedelta(days=365)

        return cls.objects.get_or_create(
            user=user,
            winner_type=winner_type,
            period_start=period_start,
            defaults={'campaign': campaign, 'selection': selection, 'period_end': period_end},
        )
