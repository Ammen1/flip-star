"""Direct messaging models: 1-on-1 conversations between users.

Design:
- Conversation: a thread between two users (M2M participants, always 2 for now).
- Message: a single message with optional soft-delete + edited_at for 15-min edit window.
- MessageRead: tracks the last-read timestamp per user per conversation so we can compute unread counts cheaply.
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone

EDIT_WINDOW_MINUTES = 15


# Local storage for message media to avoid Cloudinary's image-only limitation.
#
# This is a CALLABLE, not a FileSystemStorage instance, and that matters.
# Passing an instance to FileField(storage=...) makes Django serialize the
# instance's constructor arguments into every migration that touches the
# field -- including the absolute `location`, which is settings.MEDIA_ROOT and
# therefore differs on every machine. The repository still carries the
# evidence: committed migrations contain three different developers' absolute
# paths, e.g.
#
#   FileSystemStorage(base_url='/media/', location='C:\\Users\\...\\selfi_star\\backend\\media')
#   FileSystemStorage(base_url='/media/', location='C:\\Users\\...\\flipstar\\backend\\media')
#
# which is why `alter_message_media` migrations kept reappearing (0040, 0045,
# 0046, 0070, 0088, 0097, 0098, 0099...). It also meant `manage.py
# makemigrations --check` -- the blocking `django-checks` CI gate -- could
# never pass: a CI runner's MEDIA_ROOT matches none of those paths, so Django
# always detected a change and always wanted to write a new migration.
#
# Django serializes a callable by reference ('api.models.messaging.
# message_media_storage') and resolves it at runtime instead, so the migration
# is identical everywhere and settings.MEDIA_ROOT is still honoured exactly as
# before. Runtime behaviour is unchanged; only the serialized form differs.
def message_media_storage():
    return FileSystemStorage(
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

    def __str__(self):
        try:
            names = ', '.join(self.participants.values_list('username', flat=True)[:3])
        except Exception:
            names = 'unknown'
        return f'Conversation #{self.id} ({names})'

    def other_participant(self, user):
        """Return the other user in a 1-on-1 conversation."""
        return self.participants.exclude(id=user.id).first()

    @classmethod
    def between(cls, user_a, user_b):
        """The existing 1-on-1 conversation between two users, or None.

        The membership test cannot be written as a single annotated query.
        Chaining ``.filter(participants=a).filter(participants=b)`` is right --
        two joins, meaning "has both" -- but a ``Count('participants')`` on top
        of it counts the joined rows rather than the members, so it yields 1
        and matches nothing. Hence the explicit count per candidate, which is
        what ``list_or_create_conversations`` has always done; this is that rule
        given a name so a second caller cannot get it subtly wrong.

        Candidates are few in practice: the filter has already narrowed to
        conversations containing both users, which for 1-on-1 chats is at most
        one.
        """
        candidates = cls.objects.filter(participants=user_a).filter(participants=user_b).distinct()
        for conversation in candidates:
            if conversation.participants.count() == 2:
                return conversation
        return None


class Message(models.Model):
    MEDIA_TEXT = 'text'
    MEDIA_IMAGE = 'image'
    MEDIA_VIDEO = 'video'
    MEDIA_AUDIO = 'audio'
    MEDIA_FILE = 'file'
    # A shared post carries no uploaded file of its own -- the media it shows
    # belongs to the referenced reel -- so it is a distinct type rather than a
    # variant of image/video.
    MEDIA_POST = 'post'
    MEDIA_TYPE_CHOICES = [
        (MEDIA_TEXT, 'Text'),
        (MEDIA_IMAGE, 'Image'),
        (MEDIA_VIDEO, 'Video'),
        (MEDIA_AUDIO, 'Audio / Voice'),
        (MEDIA_FILE, 'File'),
        (MEDIA_POST, 'Shared post'),
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
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages_sent')
    text = models.TextField(blank=True, default='')
    # Use local storage for message media to avoid Cloudinary's image-only limitation
    media = models.FileField(
        upload_to='messages/%Y/%m/', null=True, blank=True, storage=message_media_storage
    )
    media_type = models.CharField(
        max_length=16,
        choices=MEDIA_TYPE_CHOICES,
        default=MEDIA_TEXT,
    )
    # A post shared into the chat, held as a reference rather than a copy.
    #
    # Sharing previously worked by appending a literal "[POST_ID:35]" marker to
    # the message text and having the client regex it back out. That carried
    # three problems this field removes: the recipient's card could show only
    # "Shared Post / Tap to view" because the text had no author, caption or
    # thumbnail to render; any user could type the marker by hand and forge a
    # share card for a post they cannot see; and a deleted post left a marker
    # pointing at nothing.
    #
    # SET_NULL rather than CASCADE: when the post goes, the conversation should
    # keep its history and show "this post is no longer available" -- deleting
    # a reel must not delete messages between two other people.
    shared_reel = models.ForeignKey(
        'api.Reel',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='shares_in_messages',
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
        max_length=16, choices=DELIVERY_STATUS_CHOICES, default=DELIVERY_SENT, db_index=True
    )
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
        ]

    def __str__(self):
        preview = (self.text or '')[:40]
        return f'Msg #{self.id} from {self.sender_id}: {preview}'

    @property
    def is_editable(self):
        """Messages can be edited within 15 minutes of creation (Instagram rule)."""
        if self.is_deleted:
            return False
        return (timezone.now() - self.created_at) <= timedelta(minutes=EDIT_WINDOW_MINUTES)


class MessageRead(models.Model):
    """Per-user, per-conversation last-read tracker — used to compute unread counts."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='message_reads')
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='reads')
    last_read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user', 'conversation')
        indexes = [
            models.Index(fields=['user', 'conversation']),
        ]

    def __str__(self):
        return (
            f'{self.user.username} read up to {self.last_read_at} in conv #{self.conversation_id}'
        )
