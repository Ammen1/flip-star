from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Campaign(models.Model):
    """Campaign for competitions and prizes"""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        # Maker/checker states. Added rather than replacing anything: a
        # campaign that never goes through approval moves draft -> active
        # exactly as before, so existing flows and existing rows are
        # untouched. Only organization campaigns are routed through
        # submitted -> approved today.
        ('submitted', 'Submitted for Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('active', 'Active'),
        ('voting', 'Voting Phase'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    CAMPAIGN_TYPES = [
        ('daily', 'Daily Campaign'),
        ('weekly', 'Weekly Campaign'),
        ('monthly', 'Monthly Campaign'),
        ('grand', 'Grand Campaign'),
    ]

    # ── Ownership ───────────────────────────────────────────────────────────
    #
    # Nullable because every campaign that already exists predates this field
    # and belongs to the platform, not to any organization. NULL therefore
    # means "a Flipstar campaign", which is the truth for existing rows --
    # inventing an owner for them would be a guess with access-control
    # consequences.
    #
    # This is never read from a request body. It is derived from the
    # authenticated user; see api/services/realms.py.
    organization = models.ForeignKey(
        'api.Organization',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='campaigns',
        help_text='Owning organization. NULL means a platform (Flipstar) campaign.',
    )

    # Who moved it through the approval workflow. Separate from created_by so
    # separation of duties can be checked: the approver must not be the author.
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaigns_submitted',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaigns_approved',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')

    title = models.CharField(max_length=200)
    description = models.TextField()
    image = models.ImageField(upload_to='campaigns/', null=True, blank=True)
    campaign_type = models.CharField(
        max_length=20,
        choices=CAMPAIGN_TYPES,
        default='grand',
        help_text='Determines rules and scoring logic',
    )

    # Link to Master Campaign (Season)
    master_campaign = models.ForeignKey(
        'MasterCampaign',
        on_delete=models.CASCADE,
        related_name='sub_campaigns',
        null=True,
        blank=True,
        help_text='Master Campaign this belongs to',
    )

    # Prize information
    prize_title = models.CharField(max_length=200)
    prize_description = models.TextField()
    prize_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Campaign status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Criteria for entry
    min_followers = models.IntegerField(default=0, help_text='Minimum followers required')
    min_level = models.IntegerField(default=1, help_text='Minimum user level required')
    min_votes_per_reel = models.IntegerField(
        default=0, help_text='Minimum votes per reel to qualify'
    )
    required_hashtags = models.CharField(
        max_length=500, blank=True, help_text='Comma-separated hashtags'
    )

    # Dates
    start_date = models.DateTimeField(null=True, blank=True)
    entry_deadline = models.DateTimeField(
        null=True, blank=True, help_text='Deadline for submitting entries'
    )
    voting_start = models.DateTimeField(null=True, blank=True, help_text='When voting begins')
    voting_end = models.DateTimeField(null=True, blank=True, help_text='When voting ends')

    # Winner information
    winner_count = models.IntegerField(
        default=1,
        help_text=(
            'Number of winners. Ignored for the four standard tiers -- Daily '
            'Sprint pays 20, Weekly Battle 10, Monthly Star 5 and the Grand '
            'Final 1, from api/services/prize_structure.py, because those '
            'counts are advertised and not an admin setting. Used only by a '
            'campaign whose type is not one of those.'
        ),
    )
    winners_announced = models.BooleanField(default=False)

    # Metadata
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='created_campaigns'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Stats
    total_entries = models.IntegerField(default=0)
    total_votes = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} ({self.status})'

    #: The timeline, in the order the campaign actually runs. Stated once so
    #: validation and any report of a broken campaign agree on what "in order"
    #: means.
    TIMELINE = (
        ('start_date', 'Start date'),
        ('entry_deadline', 'Entry deadline'),
        ('voting_start', 'Voting start'),
        ('voting_end', 'Voting end'),
    )

    def timeline_problems(self):
        """Pairs of dates that run backwards, as readable sentences.

        A campaign whose entry deadline falls after its voting end is not a
        display bug: a timezone offset is uniform, so if one instant precedes
        another it precedes it in every timezone -- rendering can collapse two
        dates onto the same day but never reverse them. Dates that appear out
        of order are stored out of order.

        Nothing prevented that. The model had no validation, the create and
        update endpoints passed the values straight through, and every layer
        below faithfully displayed what it was given.

        Blank dates are skipped rather than treated as zero: a campaign that
        has not scheduled its voting yet is incomplete, not inconsistent.
        """
        problems = []
        known = [(name, label, getattr(self, name)) for name, label in self.TIMELINE]
        filled = [(name, label, value) for name, label, value in known if value is not None]

        for (_, earlier_label, earlier), (_, later_label, later) in zip(
            filled, filled[1:], strict=False
        ):
            if earlier > later:
                problems.append(f'{earlier_label} is after {later_label}.')
        return problems

    def clean(self):
        """Refuse a timeline that runs backwards.

        Raises ValidationError so the Django admin and any serializer calling
        full_clean() both reject it, rather than each re-deriving the rule.
        """
        from django.core.exceptions import ValidationError

        problems = self.timeline_problems()
        if problems:
            raise ValidationError({'entry_deadline': problems})

    def is_active(self):
        now = timezone.now()
        if not self.start_date or not self.entry_deadline:
            return self.status == 'active'
        return self.status == 'active' and self.start_date <= now <= self.entry_deadline

    def is_voting_open(self):
        now = timezone.now()
        if not self.voting_start or not self.voting_end:
            return False
        return self.status == 'voting' and self.voting_start <= now <= self.voting_end


class CampaignEntry(models.Model):
    """User entry to a campaign"""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='entries')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='campaign_entries')
    reel = models.ForeignKey('api.Reel', on_delete=models.CASCADE, related_name='campaign_entries')

    # Entry status
    approved = models.BooleanField(default=True)
    disqualified = models.BooleanField(default=False)
    disqualification_reason = models.TextField(blank=True)

    # Voting stats
    vote_count = models.IntegerField(default=0)
    rank = models.IntegerField(null=True, blank=True)
    is_winner = models.BooleanField(default=False)

    # Metadata
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-vote_count', '-submitted_at']
        unique_together = ['campaign', 'user']
        indexes = [
            models.Index(
                fields=['campaign', 'approved', 'disqualified'], name='entry_campaign_filter_idx'
            ),
        ]

    def __str__(self):
        return f'{self.user.username} - {self.campaign.title}'


class CampaignVote(models.Model):
    """Votes for campaign entries"""

    entry = models.ForeignKey(CampaignEntry, on_delete=models.CASCADE, related_name='votes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='campaign_votes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['entry', 'user']
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} voted for {self.entry.user.username}'


class CampaignWinner(models.Model):
    """Winners of campaigns"""

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='winners')
    entry = models.ForeignKey(
        CampaignEntry, on_delete=models.CASCADE, related_name='winner_records'
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='campaign_wins')

    rank = models.IntegerField(help_text='1st, 2nd, 3rd place, etc.')
    prize_claimed = models.BooleanField(default=False)
    prize_claimed_at = models.DateTimeField(null=True, blank=True)

    announced_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['rank']
        unique_together = ['campaign', 'rank']

    def __str__(self):
        return f'{self.user.username} - {self.campaign.title} (Rank {self.rank})'


class CampaignNotification(models.Model):
    """Notifications related to campaigns"""

    NOTIFICATION_TYPES = [
        ('new_campaign', 'New Campaign'),
        ('entry_approved', 'Entry Approved'),
        ('voting_started', 'Voting Started'),
        ('winner_announced', 'Winner Announced'),
        ('prize_ready', 'Prize Ready'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='notifications')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='campaign_notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.notification_type} - {self.user.username}'
