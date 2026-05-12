from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import secrets

class APIKey(models.Model):
    """API Keys for third-party integrations"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=100)
    key = models.CharField(max_length=64, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} - {self.key[:8]}..."
    
    class Meta:
        ordering = ['-created_at']

class PlatformSettings(models.Model):
    """Global platform settings"""
    # General Settings
    platform_name = models.CharField(max_length=100, default='Selfie Star')
    platform_description = models.TextField(default='Social media platform for creators')
    maintenance_mode = models.BooleanField(default=False)
    allow_registrations = models.BooleanField(default=True)
    require_email_verification = models.BooleanField(default=False)
    
    # Content Settings
    max_file_size_mb = models.IntegerField(default=50)
    allowed_video_formats = models.CharField(max_length=200, default='mp4,mov,avi')
    allowed_image_formats = models.CharField(max_length=200, default='jpg,jpeg,png,gif')
    max_caption_length = models.IntegerField(default=2200)
    enable_comments = models.BooleanField(default=True)
    enable_voting = models.BooleanField(default=True)
    
    # Moderation Settings
    auto_moderation = models.BooleanField(default=False)
    profanity_filter = models.BooleanField(default=True)
    spam_detection = models.BooleanField(default=True)
    
    # Notification Settings
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    
    # Performance Settings
    cache_enabled = models.BooleanField(default=True)
    cdn_enabled = models.BooleanField(default=False)
    cdn_url = models.URLField(blank=True, null=True)
    
    # API Settings
    api_rate_limit = models.IntegerField(default=100, help_text='Requests per minute')
    api_enabled = models.BooleanField(default=True)
    
    # Analytics
    analytics_enabled = models.BooleanField(default=True)
    track_user_activity = models.BooleanField(default=True)
    
    # Typography Settings
    font_family_primary = models.CharField(max_length=100, default='Inter', help_text='Primary font for headings and UI')
    font_family_secondary = models.CharField(max_length=100, default='Inter', help_text='Secondary font for body text')
    font_family_username = models.CharField(max_length=100, default='Inter', help_text='Font for usernames')
    font_family_caption = models.CharField(max_length=100, default='Inter', help_text='Font for captions and descriptions')
    font_size_base = models.IntegerField(default=16, help_text='Base font size in pixels')
    font_weight_headings = models.CharField(max_length=10, default='700', help_text='Font weight for headings')
    font_weight_body = models.CharField(max_length=10, default='400', help_text='Font weight for body text')
    letter_spacing = models.CharField(max_length=20, default='normal', help_text='Letter spacing (e.g., normal, 0.5px, -0.02em)')
    line_height = models.CharField(max_length=10, default='1.5', help_text='Line height multiplier')
    
    # Theme Colors (for future use)
    primary_color = models.CharField(max_length=20, default='#8B5CF6', help_text='Primary brand color')
    secondary_color = models.CharField(max_length=20, default='#F97316', help_text='Secondary/accent color')
    
    # Global Theme Settings (applies to all users)
    theme_preset = models.CharField(max_length=50, default='flipstar', help_text='Theme preset name (flipstar, ocean, forest, etc.)')
    dark_mode_default = models.BooleanField(default=False, help_text='Default dark mode for all users')
    primary_color_override = models.CharField(max_length=200, blank=True, null=True, help_text='Custom primary color or gradient override')
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        verbose_name = 'Platform Settings'
        verbose_name_plural = 'Platform Settings'
    
    def __str__(self):
        return f"Platform Settings - {self.platform_name}"

class SystemLog(models.Model):
    """System activity logs"""
    LOG_TYPES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
        ('security', 'Security'),
    ]
    
    log_type = models.CharField(max_length=20, choices=LOG_TYPES)
    message = models.TextField()
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    endpoint = models.CharField(max_length=200, blank=True)
    details = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['log_type']),
        ]
    
    def __str__(self):
        return f"[{self.log_type.upper()}] {self.message[:50]}"

class PlatformMetrics(models.Model):
    """Daily platform metrics snapshot"""
    date = models.DateField(unique=True)
    
    # User Metrics
    total_users = models.IntegerField(default=0)
    active_users = models.IntegerField(default=0)
    new_users = models.IntegerField(default=0)
    
    # Content Metrics
    total_reels = models.IntegerField(default=0)
    new_reels = models.IntegerField(default=0)
    total_comments = models.IntegerField(default=0)
    new_comments = models.IntegerField(default=0)
    
    # Engagement Metrics
    total_votes = models.IntegerField(default=0)
    new_votes = models.IntegerField(default=0)
    total_follows = models.IntegerField(default=0)
    new_follows = models.IntegerField(default=0)
    
    # Performance Metrics
    avg_response_time_ms = models.FloatField(default=0)
    error_rate = models.FloatField(default=0)
    api_calls = models.IntegerField(default=0)
    
    # Revenue Metrics
    paid_subscriptions = models.IntegerField(default=0)
    revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date']
        verbose_name = 'Platform Metrics'
        verbose_name_plural = 'Platform Metrics'
    
    def __str__(self):
        return f"Metrics for {self.date}"

class AdminNotification(models.Model):
    """Notifications for admin users"""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    is_read = models.BooleanField(default=False)
    action_url = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"[{self.priority.upper()}] {self.title}"
