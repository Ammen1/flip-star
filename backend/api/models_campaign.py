from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Campaign(models.Model):
    """Campaign for competitions and prizes"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
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
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    image = models.ImageField(upload_to='campaigns/', null=True, blank=True)
    campaign_type = models.CharField(max_length=20, choices=CAMPAIGN_TYPES, default='grand', help_text='Determines rules and scoring logic')
    
    # Link to Master Campaign (Season)
    master_campaign = models.ForeignKey('MasterCampaign', on_delete=models.CASCADE, related_name='sub_campaigns', null=True, blank=True, help_text='Master Campaign this belongs to')
    
    # Prize information
    prize_title = models.CharField(max_length=200)
    prize_description = models.TextField()
    prize_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Campaign status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Criteria for entry
    min_followers = models.IntegerField(default=0, help_text='Minimum followers required')
    min_level = models.IntegerField(default=1, help_text='Minimum user level required')
    min_votes_per_reel = models.IntegerField(default=0, help_text='Minimum votes per reel to qualify')
    required_hashtags = models.CharField(max_length=500, blank=True, help_text='Comma-separated hashtags')
    
    # Dates
    start_date = models.DateTimeField(null=True, blank=True)
    entry_deadline = models.DateTimeField(null=True, blank=True, help_text='Deadline for submitting entries')
    voting_start = models.DateTimeField(null=True, blank=True, help_text='When voting begins')
    voting_end = models.DateTimeField(null=True, blank=True, help_text='When voting ends')
    
    # Winner information
    winner_count = models.IntegerField(default=1, help_text='Number of winners')
    winners_announced = models.BooleanField(default=False)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_campaigns')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Stats
    total_entries = models.IntegerField(default=0)
    total_votes = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} ({self.status})"
    
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
            models.Index(fields=['campaign', 'approved', 'disqualified'], name='entry_campaign_filter_idx'),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.campaign.title}"

class CampaignVote(models.Model):
    """Votes for campaign entries"""
    entry = models.ForeignKey(CampaignEntry, on_delete=models.CASCADE, related_name='votes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='campaign_votes')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['entry', 'user']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} voted for {self.entry.user.username}"

class CampaignWinner(models.Model):
    """Winners of campaigns"""
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='winners')
    entry = models.ForeignKey(CampaignEntry, on_delete=models.CASCADE, related_name='winner_records')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='campaign_wins')
    
    rank = models.IntegerField(help_text='1st, 2nd, 3rd place, etc.')
    prize_claimed = models.BooleanField(default=False)
    prize_claimed_at = models.DateTimeField(null=True, blank=True)
    
    announced_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['rank']
        unique_together = ['campaign', 'rank']
    
    def __str__(self):
        return f"{self.user.username} - {self.campaign.title} (Rank {self.rank})"

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
        return f"{self.notification_type} - {self.user.username}"
