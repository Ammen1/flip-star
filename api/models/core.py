"""
Core social models: profiles, reels, comments, follows, reports, notifications.

Domain-specific models live in sibling modules (``wallet``, ``subscription``,
``campaign``, ...). ``api/models/__init__.py`` re-exports every model, so
``from api.models import X`` continues to resolve for all of them.
"""

from django.contrib.auth.models import User
from django.db import models, transaction
from django.utils import timezone

# Concrete relation target. Everything else this module references across
# module boundaries is declared as a string ('Campaign', 'CampaignTheme') and
# resolved lazily by Django, which keeps the import graph acyclic.
from .boost import BoostCampaign


class Category(models.Model):
    """Content categories for posts - admin-managed"""
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text='Icon name (e.g., dance, comedy, etc.)')
    order = models.IntegerField(default=0, help_text='Display order')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    bio = models.TextField(blank=True)
    xp = models.IntegerField(default=0)
    level = models.IntegerField(default=1)
    streak = models.IntegerField(default=0)
    last_checkin = models.DateTimeField(null=True, blank=True)
    language = models.CharField(max_length=10, default='en')
    
    # Gamification - Coins
    coins = models.IntegerField(default=0, help_text='User coin balance')
    coins_earned_total = models.IntegerField(default=0, help_text='Total coins earned lifetime')
    coins_spent_total = models.IntegerField(default=0, help_text='Total coins spent lifetime')
    
    # Gamification - Points (for withdrawals and transfers as birr)
    points = models.IntegerField(default=0, help_text='User point balance (convertible to birr)')
    points_earned_total = models.IntegerField(default=0, help_text='Total points earned lifetime')
    points_withdrawn_total = models.IntegerField(default=0, help_text='Total points withdrawn lifetime')
    
    # Gamification - Daily Spin
    last_spin_date = models.DateField(null=True, blank=True, help_text='Last daily spin date')
    spins_total = models.IntegerField(default=0, help_text='Total spins done')
    
    # Gamification - Login Streak
    login_streak = models.IntegerField(default=0, help_text='Consecutive login days')
    last_login_date = models.DateField(null=True, blank=True)
    longest_login_streak = models.IntegerField(default=0)
    
    # Privacy Settings
    allow_mentions = models.BooleanField(default=True, help_text='Allow other users to mention you in comments')
    
    # Gamification - Gifts
    gifts_sent_today = models.IntegerField(default=0)
    gifts_received_today = models.IntegerField(default=0)
    gifts_sent_total = models.IntegerField(default=0)
    gifts_received_total = models.IntegerField(default=0)
    last_gift_reset = models.DateField(null=True, blank=True, help_text='Last daily gift counter reset')
    
    # Ethiopian phone number (e.g. +251912345678) — set during phone-OTP registration
    phone_number = models.CharField(max_length=20, blank=True, null=True, unique=True)
    
    # Free trial tracking for first-time subscribers
    has_used_free_trial = models.BooleanField(default=False, help_text='User has used their 1-day free trial')
    
    # Trial tracking
    trial_start_date = models.DateTimeField(null=True, blank=True, help_text='When 3-day trial started')
    trial_end_date = models.DateTimeField(null=True, blank=True, help_text='When 3-day trial ends')
    is_trial_user = models.BooleanField(default=True, help_text='User is in trial period')
    trial_popup_shown_count = models.IntegerField(default=0, help_text='How many times popup shown')
    trial_interaction_count = models.IntegerField(default=0, help_text='How many interactions attempted')
    
    # OTP tracking
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_expires_at = models.DateTimeField(null=True, blank=True)
    otp_attempts = models.IntegerField(default=0)

    # Push notifications
    fcm_token = models.CharField(max_length=512, blank=True, default='')

    # Privacy settings
    is_private = models.BooleanField(default=False)
    show_activity = models.BooleanField(default=True)
    allow_messages = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    
    # Moderation
    is_shadowbanned = models.BooleanField(default=False, help_text='User is shadow banned - content hidden from others but visible to self')
    ban_expires_at = models.DateTimeField(null=True, blank=True, help_text='When temporary ban expires (null if not temp banned)')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - Level {self.level}"

    def is_telebirr_user(self):
        """Whether this user has ever paid via Telebirr -- used to gate
        Telebirr B2C cash payouts (winner gifts) to users Telebirr can
        actually reach."""
        from .subscription import SubscriptionPayment
        return SubscriptionPayment.objects.filter(user=self.user, payment_method='telebirr').exists()

    def _apply_delta(self, field, delta, *, total_field=None):
        """
        Atomically add (delta > 0) or deduct (delta < 0) `field` (`points` or
        `coins`), row-locked for the duration of a short transaction.

        Call sites across the app used to do `profile.points += x` /
        `profile.save()` directly against whatever copy of the row they
        happened to hold -- under concurrent requests (a gift arriving while
        a withdrawal is being requested, two rapid taps on the same action)
        that loses updates or lets a deduction succeed against a balance
        that was already spent by another request in the meantime. Locking
        the row and re-reading it fresh here, rather than trusting
        `self`'s in-memory value, is what actually prevents that.

        Raises ValueError, without writing anything, if a deduction would
        take `field` negative. `total_field`, if given, is the name of a
        lifetime-total counter (e.g. `points_earned_total`,
        `coins_spent_total`) incremented by `abs(delta)` in the same locked
        transaction.
        """
        if delta == 0:
            raise ValueError('delta must not be zero')

        with transaction.atomic():
            locked = UserProfile.objects.select_for_update().get(pk=self.pk)
            current = getattr(locked, field) or 0
            new_value = current + delta
            if new_value < 0:
                raise ValueError(f'Insufficient {field}. Have {current}, need {-delta}')
            setattr(locked, field, new_value)
            update_fields = [field]
            if total_field:
                setattr(locked, total_field, (getattr(locked, total_field) or 0) + abs(delta))
                update_fields.append(total_field)
            locked.save(update_fields=update_fields)

        setattr(self, field, getattr(locked, field))
        if total_field:
            setattr(self, total_field, getattr(locked, total_field))

    def add_points(self, amount, total_field='points_earned_total'):
        if amount <= 0:
            raise ValueError('Amount must be positive')
        self._apply_delta('points', amount, total_field=total_field)

    def deduct_points(self, amount, total_field=None):
        """Raises ValueError (no partial write) if points would go negative."""
        if amount <= 0:
            raise ValueError('Amount must be positive')
        self._apply_delta('points', -amount, total_field=total_field)

    def add_coins(self, amount, total_field='coins_earned_total'):
        if amount <= 0:
            raise ValueError('Amount must be positive')
        self._apply_delta('coins', amount, total_field=total_field)

    def deduct_coins(self, amount, total_field='coins_spent_total'):
        """Raises ValueError (no partial write) if coins would go negative."""
        if amount <= 0:
            raise ValueError('Amount must be positive')
        self._apply_delta('coins', -amount, total_field=total_field)


class Draft(models.Model):
    """An unpublished reel-in-progress, saved so a user can resume editing later."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='drafts')
    image = models.ImageField(upload_to='drafts/', null=True, blank=True)
    media = models.FileField(upload_to='drafts/', null=True, blank=True)
    caption = models.TextField(blank=True)
    hashtags = models.TextField(blank=True)
    overlay_text = models.TextField(blank=True, default='')
    filter = models.CharField(max_length=50, blank=True, default='none')

    # Audio for video drafts
    audio_file = models.FileField(upload_to='drafts/audio/', null=True, blank=True)
    audio_volume_level = models.IntegerField(default=80)
    original_volume_level = models.IntegerField(default=100)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Draft by {self.user.username} - {self.created_at}"


class Reel(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reels')
    image = models.ImageField(upload_to='reels/', null=True, blank=True)
    media = models.FileField(upload_to='reels/', null=True, blank=True)
    caption = models.TextField(blank=True)
    hashtags = models.TextField(blank=True)
    overlay_text = models.TextField(blank=True, default='')
    votes = models.IntegerField(default=0)
    view_count = models.PositiveBigIntegerField(default=0)
    shares = models.IntegerField(default=0)

    # Category
    category = models.ForeignKey('Category', on_delete=models.SET_NULL, null=True, blank=True, related_name='reels')

    # Campaign integration
    campaign = models.ForeignKey('Campaign', on_delete=models.SET_NULL, null=True, blank=True, related_name='campaign_posts')
    theme = models.ForeignKey('CampaignTheme', on_delete=models.SET_NULL, null=True, blank=True, related_name='theme_posts')
    is_campaign_post = models.BooleanField(default=False)

    # Media processing
    thumbnail = models.ImageField(upload_to='thumbnails/', null=True, blank=True)
    blurhash = models.CharField(max_length=100, blank=True, default='')
    duration = models.FloatField(null=True, blank=True)
    processed = models.BooleanField(default=False)

    # Boost functionality
    is_boosted = models.BooleanField(default=False, help_text='Whether this post is currently boosted')
    active_boost_campaign = models.ForeignKey(
        BoostCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='boosted_reels',
        help_text='Currently active boost campaign for this post'
    )
    total_boost_impressions = models.IntegerField(default=0, help_text='Total impressions from all boost campaigns')
    total_boost_engagements = models.IntegerField(default=0, help_text='Total engagements from all boost campaigns')

    # Moderation
    is_hidden = models.BooleanField(default=False, help_text='Content is hidden/removed by moderation (soft-delete)')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['campaign', '-created_at']),
            models.Index(fields=['is_campaign_post', '-created_at']),
            models.Index(fields=['is_boosted', '-created_at']),
        ]

    def __str__(self):
        return f"Reel by {self.user.username}"
    
    def get_hashtags_list(self):
        if self.hashtags:
            return [tag.strip() for tag in self.hashtags.split(',') if tag.strip()]
        return []

class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    reel = models.ForeignKey(Reel, on_delete=models.CASCADE, related_name='comments')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            # Speeds up the per-reel recent-comments prefetch used by the feed
            models.Index(fields=['reel', '-created_at']),
        ]

    def __str__(self):
        return f"Comment by {self.user.username} on {self.reel.id}"
    
    @property
    def likes_count(self):
        return self.comment_likes.count()
    
    @property
    def replies_count(self):
        return self.replies.count()
    
    @property
    def is_editable(self):
        """Comments can be edited within 15 minutes of creation (similar to messages)."""
        if self.is_deleted:
            return False
        from datetime import timedelta
        return (timezone.now() - self.created_at) <= timedelta(minutes=15)

class CommentLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comment_likes')
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='comment_likes', null=True, blank=True)
    reply = models.ForeignKey('CommentReply', on_delete=models.CASCADE, related_name='reply_likes', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'comment'],
                condition=models.Q(comment__isnull=False),
                name='unique_user_comment_like'
            ),
            models.UniqueConstraint(
                fields=['user', 'reply'],
                condition=models.Q(reply__isnull=False),
                name='unique_user_reply_like'
            ),
        ]
        ordering = ['-created_at']

    def __str__(self):
        if self.comment:
            return f"{self.user.username} liked comment {self.comment.id}"
        if self.reply:
            return f"{self.user.username} liked reply {self.reply.id}"
        return f"{self.user.username} like"

class CommentReply(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comment_replies')
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='replies')
    parent_reply = models.ForeignKey('self', on_delete=models.CASCADE, related_name='child_replies', null=True, blank=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        parent = f"reply {self.parent_reply.id}" if self.parent_reply else f"comment {self.comment.id}"
        return f"Reply by {self.user.username} on {parent}"
    
    @property
    def likes_count(self):
        return self.reply_likes.count()
    
    @property
    def is_editable(self):
        """Replies can be edited within 15 minutes of creation."""
        if self.is_deleted:
            return False
        from datetime import timedelta
        return (timezone.now() - self.created_at) <= timedelta(minutes=15)

class Mention(models.Model):
    """Track mentions of users in comments and replies."""
    mentioned_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mentions_received')
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='mentions', null=True, blank=True)
    reply = models.ForeignKey(CommentReply, on_delete=models.CASCADE, related_name='mentions', null=True, blank=True)
    mentioned_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mentions_sent')
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['mentioned_user', 'created_at']),
            models.Index(fields=['comment']),
            models.Index(fields=['reply']),
        ]

    def __str__(self):
        target = f"reply {self.reply.id}" if self.reply else f"comment {self.comment.id}"
        return f"{self.mentioned_by.username} mentioned {self.mentioned_user.username} in {target}"

class SavedPost(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_posts')
    reel = models.ForeignKey(Reel, on_delete=models.CASCADE, related_name='saved_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'reel')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} saved reel {self.reel.id}"

class Vote(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reel = models.ForeignKey(Reel, on_delete=models.CASCADE, related_name='reel_votes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'reel')
        indexes = [
            models.Index(fields=['user', 'reel']),
        ]

    def __str__(self):
        return f"{self.user.username} voted on {self.reel.id}"

class Quest(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    xp_reward = models.IntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class UserQuest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    quest = models.ForeignKey(Quest, on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'quest')

    def __str__(self):
        return f"{self.user.username} - {self.quest.title}"

class Subscription(models.Model):
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('premium', 'Premium'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.plan}"

class NotificationPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_prefs')
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    phone = models.CharField(max_length=20, blank=True)
    # Specific notification type preferences
    likes = models.BooleanField(default=True)
    comments = models.BooleanField(default=True)
    follows = models.BooleanField(default=True)
    messages = models.BooleanField(default=True)
    mentions = models.BooleanField(default=True)

    def __str__(self):
        return f"Notifications for {self.user.username}"

class Competition(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    prize = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

class Winner(models.Model):
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name='winners')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wins')
    reel = models.ForeignKey(Reel, on_delete=models.CASCADE, related_name='wins', null=True, blank=True)
    votes_received = models.IntegerField(default=0)
    prize_claimed = models.BooleanField(default=False)
    announced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-announced_at']

    def __str__(self):
        return f"{self.user.username} - {self.competition.title}"

class Report(models.Model):
    REPORT_TYPES = [
        ('inappropriate', 'Inappropriate Content'),
        ('spam', 'Spam'),
        ('harassment', 'Harassment'),
        ('copyright', 'Copyright Violation'),
        ('scam', 'Scam/Fraud'),
        ('hate_speech', 'Hate Speech'),
        ('self_harm', 'Self Harm'),
        ('violence', 'Violence'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewing', 'Under Review'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]

    TARGET_TYPES = [
        ('reel', 'Reel'),
        ('comment', 'Comment'),
        ('user', 'User'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    reported_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_made')
    reported_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_received', null=True, blank=True)
    reported_reel = models.ForeignKey(Reel, on_delete=models.CASCADE, related_name='reports', null=True, blank=True)
    reported_comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='reports', null=True, blank=True)
    target_type = models.CharField(max_length=20, choices=TARGET_TYPES, default='reel')
    report_type = models.CharField(max_length=50, choices=REPORT_TYPES)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    resolution_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reports_reviewed')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Report #{self.id} - {self.report_type} by {self.reported_by.username}"


class ModerationAction(models.Model):
    ACTION_CHOICES = [
        ('warning', 'Warning Issued'),
        ('content_removed', 'Content Removed'),
        ('shadowban', 'Shadow Banned'),
        ('temp_ban', 'Temporary Ban'),
        ('permanent_ban', 'Permanent Ban'),
        ('no_action', 'No Action Taken'),
    ]

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='moderation_actions')
    moderator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='moderation_actions_taken')
    action_taken = models.CharField(max_length=30, choices=ACTION_CHOICES)
    reason_details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    undone = models.BooleanField(default=False)
    undone_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderation_actions_undone')
    undone_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Action #{self.id}: {self.action_taken} on Report #{self.report_id}"

class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following')
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['follower', 'following']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"

class Block(models.Model):
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_users')
    blocked = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['blocker', 'blocked']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.blocker.username} blocked {self.blocked.username}"

class Notification(models.Model):
    """General notifications for user activities (likes, comments, follows, etc.)"""
    NOTIFICATION_TYPES = [
        ('like', 'Like'),
        ('comment', 'Comment'),
        ('follow', 'Follow'),
        ('mention', 'Mention'),
        ('gift', 'Gift'),
        ('moderation', 'Moderation Action'),
    ]
    
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications_sent')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    reel = models.ForeignKey(Reel, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.notification_type} notification for {self.recipient.username}"


class NotInterested(models.Model):
    """Tracks reels a user marked as 'not interested' to hide from their feed"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='not_interested_reels')
    reel = models.ForeignKey(Reel, on_delete=models.CASCADE, related_name='not_interested_by')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'reel')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'reel']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} not interested in reel {self.reel.id}"


class PushSubscription(models.Model):
    """Web Push (VAPID) subscription for a user's browser.

    Each browser/device produces a unique `endpoint`. We store the public-key
    material (`p256dh`) and `auth` secret returned by the PushManager so the
    server can sign and encrypt push payloads.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.URLField(max_length=600, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [models.Index(fields=['user'])]

    def __str__(self):
        return f"PushSubscription({self.user.username}, {self.endpoint[:40]}…)"
