"""Support / Help request models."""
from django.contrib.auth.models import User
from django.db import models


class SupportRequest(models.Model):
    """A user-submitted support / help request handled by admins."""

    CATEGORY_CHOICES = [
        ('account', 'Account'),
        ('payment', 'Payment / Wallet'),
        ('technical', 'Technical Issue'),
        ('content', 'Content / Post'),
        ('abuse', 'Abuse / Report'),
        ('suggestion', 'Suggestion / Feedback'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('received', 'Received'),
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('solved', 'Solved'),
        ('closed', 'Closed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_requests')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='received')
    admin_response = models.TextField(blank=True, default='')
    handled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='handled_support_requests'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'support_requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f'{self.user.username}: {self.subject} ({self.status})'
