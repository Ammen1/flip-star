"""Direct messaging models: 1-on-1 conversations between users.

Design:
- Conversation: a thread between two users (M2M participants, always 2 for now).
- Message: a single message with optional soft-delete + edited_at for 15-min edit window.
- MessageRead: tracks the last-read timestamp per user per conversation so we can compute unread counts cheaply.
"""
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from datetime import timedelta


EDIT_WINDOW_MINUTES = 15

# Local storage for message media to avoid Cloudinary's image-only limitation
message_media_storage = FileSystemStorage(
    location=settings.MEDIA_ROOT,
    base_url=settings.MEDIA_URL,
)


class Conversation(models.Model):
    participants = models.ManyToManyField(User, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    # Bumped whenever a new message is added so we can sort inbox efficiently.
    last_message_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-last_message_at']
        indexes = [
            models.Index(fields=['-last_message_at']),
        ]

    def other_participant(self, user):
        """Return the other user in a 1-on-1 conversation."""
        return self.participants.exclude(id=user.id).first()

    def __str__(self):
        try:
            names = ', '.join(self.participants.values_list('username', flat=True)[:3])
        except Exception:
            names = 'unknown'
        return f"Conversation #{self.id} ({names})"


class Message(models.Model):
    MEDIA_TEXT = 'text'
    MEDIA_IMAGE = 'image'
    MEDIA_VIDEO = 'video'
    MEDIA_AUDIO = 'audio'
    MEDIA_FILE = 'file'
    MEDIA_TYPE_CHOICES = [
        (MEDIA_TEXT, 'Text'),
        (MEDIA_IMAGE, 'Image'),
        (MEDIA_VIDEO, 'Video'),
        (MEDIA_AUDIO, 'Audio / Voice'),
        (MEDIA_FILE, 'File'),
    ]
    
    DELIVERY_SENDING = 'sending'
    DELIVERY_SENT = 'sent'
    DELIVERY_DELIVERED = 'delivered'
    DELIVERY_READ = 'read'
    DELIVERY_STATUS_CHOICES = [
        (DELIVERY_SENDING, 'Sending'),
        (DELIVERY_SENT, 'Sent'),
        (DELIVERY_DELIVERED, 'Delivered'),
        (DELIVERY_READ, 'Read'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages'
    )
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='messages_sent'
    )
    text = models.TextField(blank=True, default='')
    # Use local storage for message media to avoid Cloudinary's image-only limitation
    media = models.FileField(
        upload_to='messages/%Y/%m/',
        null=True,
        blank=True,
        storage=message_media_storage
    )
    media_type = models.CharField(
        max_length=16, choices=MEDIA_TYPE_CHOICES, default=MEDIA_TEXT,
    )
    media_name = models.CharField(max_length=255, blank=True, default='')
    media_size = models.PositiveIntegerField(null=True, blank=True)
    # Duration in seconds — for audio/voice notes and videos.
    media_duration = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    # Delivery lifecycle fields
    delivery_status = models.CharField(
        max_length=16, choices=DELIVERY_STATUS_CHOICES, default=DELIVERY_SENT,
        db_index=True
    )
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
        ]

    @property
    def is_editable(self):
        """Messages can be edited within 15 minutes of creation (Instagram rule)."""
        if self.is_deleted:
            return False
        return (timezone.now() - self.created_at) <= timedelta(minutes=EDIT_WINDOW_MINUTES)

    def __str__(self):
        preview = (self.text or '')[:40]
        return f"Msg #{self.id} from {self.sender_id}: {preview}"


class MessageRead(models.Model):
    """Per-user, per-conversation last-read tracker — used to compute unread counts."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='message_reads')
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='reads'
    )
    last_read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user', 'conversation')
        indexes = [
            models.Index(fields=['user', 'conversation']),
        ]

    def __str__(self):
        return f"{self.user.username} read up to {self.last_read_at} in conv #{self.conversation_id}"
