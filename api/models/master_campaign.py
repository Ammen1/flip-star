from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class MasterCampaign(models.Model):
    """Master Campaign (Season) - Container for all campaign types"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('upcoming', 'Upcoming'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Basic Information
    title = models.CharField(max_length=200, help_text='e.g., "Season 1 Campaign"')
    description = models.TextField(help_text='Overall description of the season')
    image = models.ImageField(upload_to='master_campaigns/', null=True, blank=True)
    
    # Campaign Duration
    start_date = models.DateTimeField(help_text='When the master campaign starts')
    end_date = models.DateTimeField(help_text='When the master campaign ends')
    
    # Status and Control
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Auto-generation settings
    auto_generate_daily = models.BooleanField(default=True, help_text='Automatically generate daily campaigns')
    auto_generate_weekly = models.BooleanField(default=True, help_text='Automatically generate weekly campaigns')
    auto_generate_monthly = models.BooleanField(default=True, help_text='Automatically generate monthly campaigns')
    auto_generate_grand = models.BooleanField(default=True, help_text='Automatically generate grand campaign')
    
    # Generation configuration - how many of each type to generate
    daily_campaign_count = models.IntegerField(default=0, help_text='Number of daily campaigns (0 = all days in range)')
    weekly_campaign_count = models.IntegerField(default=0, help_text='Number of weekly campaigns (0 = all weeks in range)')
    monthly_campaign_count = models.IntegerField(default=0, help_text='Number of monthly campaigns (0 = all months in range)')
    grand_campaign_count = models.IntegerField(default=1, help_text='Number of grand campaigns (usually 1)')
    
    # Entry Requirements (inherited by sub-campaigns)
    min_followers = models.IntegerField(default=0, help_text='Minimum followers required to join')
    min_level = models.IntegerField(default=1, help_text='Minimum user level required')
    required_hashtags = models.CharField(max_length=500, blank=True, help_text='Comma-separated hashtags for all campaigns')
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_master_campaigns')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Statistics
    total_participants = models.IntegerField(default=0)
    total_daily_campaigns = models.IntegerField(default=0)
    total_weekly_campaigns = models.IntegerField(default=0)
    total_monthly_campaigns = models.IntegerField(default=0)
    total_grand_campaigns = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} ({self.status})"
    
    def is_active(self):
        now = timezone.now()
        return self.status == 'active' and self.start_date <= now <= self.end_date
    
    def is_upcoming(self):
        now = timezone.now()
        return self.status == 'upcoming' and now < self.start_date
    
    def is_completed(self):
        return self.status == 'completed' or timezone.now() > self.end_date
    
    def get_duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days
        return 0
    
    def get_current_phase(self):
        now = timezone.now()
        if not self.start_date or not self.end_date:
            return 'not_configured'
        
        if now < self.start_date:
            return 'upcoming'
        elif now > self.end_date:
            return 'completed'
        else:
            return 'active'

class MasterCampaignParticipant(models.Model):
    """Users participating in a Master Campaign"""
    
    master_campaign = models.ForeignKey(MasterCampaign, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='master_campaign_participations')
    
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    # Statistics within this master campaign
    total_daily_wins = models.IntegerField(default=0)
    total_weekly_wins = models.IntegerField(default=0)
    total_monthly_wins = models.IntegerField(default=0)
    total_grand_wins = models.IntegerField(default=0)
    
    # Overall score accumulation
    total_score = models.IntegerField(default=0)
    total_posts = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ['master_campaign', 'user']
        ordering = ['-total_score']
    
    def __str__(self):
        return f"{self.user.username} - {self.master_campaign.title}"
