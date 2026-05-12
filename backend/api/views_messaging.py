"""Direct messaging views.

Endpoints:
- GET    /messages/conversations/                 list my conversations
- POST   /messages/conversations/                 create or fetch a 1-on-1 conversation (body: {user_id})
- GET    /messages/conversations/<id>/messages/   list messages (newest last)
- POST   /messages/conversations/<id>/messages/   send a message (body: {text})
- PATCH  /messages/<id>/                          edit own message within 15 min (body: {text})
- DELETE /messages/<id>/                          soft-delete own message
- POST   /messages/conversations/<id>/read/       mark conversation as read up to now
- GET    /messages/unread-count/                  total unread DM count (for badge)
- GET    /messages/users/search/?q=...            search users to start a new chat
"""
from django.contrib.auth.models import User
from django.db.models import Q, Max, Count, OuterRef, Subquery, IntegerField, F
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models_messaging import Conversation, Message, MessageRead
from .serializers_messaging import (
    BriefUserSerializer,
    ConversationSerializer,
    MessageSerializer,
)


# ─── Conversation list / create ───────────────────────────────────────────────
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def list_or_create_conversations(request):
    if request.method == 'GET':
        # IMPORTANT: do NOT prefetch all messages — a chatty conversation could
        # load thousands of rows just to render the inbox.  Instead we annotate
        # exactly the fields the serializer needs so the whole inbox resolves
        # in O(1) queries instead of O(N) per-conversation lookups.
        last_msg = Message.objects.filter(conversation=OuterRef('pk')).order_by('-created_at')
        read_marker = MessageRead.objects.filter(
            conversation=OuterRef('pk'), user=request.user,
        ).values('last_read_at')[:1]

        # Unread count — count messages in this conversation not sent by me,
        # newer than my last_read_at (or all of them if I have no marker yet).
        # Uses nested OuterRef so Django resolves it as a single correlated
        # subquery against the outer conversation row.
        unread_count_sq = (
            Message.objects
            .filter(conversation=OuterRef('pk'))
            .exclude(sender=request.user)
            .annotate(_my_read_at=Subquery(
                MessageRead.objects.filter(
                    conversation=OuterRef(OuterRef('pk')),
                    user=request.user,
                ).values('last_read_at')[:1]
            ))
            .filter(Q(_my_read_at__isnull=True) | Q(created_at__gt=F('_my_read_at')))
            .values('conversation')
            .annotate(c=Count('id'))
            .values('c')
        )

        qs = (
            request.user.conversations
            .prefetch_related('participants', 'participants__profile')
            .annotate(
                _last_msg_id=Subquery(last_msg.values('id')[:1]),
                _last_msg_text=Subquery(last_msg.values('text')[:1]),
                _last_msg_sender_id=Subquery(last_msg.values('sender_id')[:1]),
                _last_msg_media_type=Subquery(last_msg.values('media_type')[:1]),
                _last_msg_is_deleted=Subquery(last_msg.values('is_deleted')[:1]),
                _last_msg_created_at=Subquery(last_msg.values('created_at')[:1]),
                _last_read_at=Subquery(read_marker),
                _unread_total=Coalesce(Subquery(
                    unread_count_sq.values('conversation')
                    .annotate(c=Count('id')).values('c')[:1],
                    output_field=IntegerField(),
                ), 0),
            )
            .order_by('-last_message_at')
        )
        data = ConversationSerializer(qs, many=True, context={'request': request}).data
        return Response(data)

    # POST: create or return an existing 1-on-1 conversation
    other_id = request.data.get('user_id')
    if not other_id:
        return Response({'error': 'user_id is required'}, status=400)
    try:
        other_id = int(other_id)
    except (TypeError, ValueError):
        return Response({'error': 'user_id must be an integer'}, status=400)
    if other_id == request.user.id:
        return Response({'error': "You can't message yourself"}, status=400)

    other = User.objects.filter(id=other_id).first()
    if not other:
        return Response({'error': 'User not found'}, status=404)

    # Find an existing 1-on-1 conversation between these two users
    existing = (
        Conversation.objects
        .filter(participants=request.user)
        .filter(participants=other)
        .distinct()
    )
    # Pick the first one where participant count is exactly 2
    for conv in existing:
        if conv.participants.count() == 2:
            data = ConversationSerializer(conv, context={'request': request}).data
            return Response(data, status=200)

    # Otherwise create a new one
    conv = Conversation.objects.create()
    conv.participants.add(request.user, other)
    data = ConversationSerializer(conv, context={'request': request}).data
    return Response(data, status=201)


def _infer_media_type(upload, explicit=None):
    """Figure out a media_type value from content-type / filename."""
    if explicit in (Message.MEDIA_IMAGE, Message.MEDIA_VIDEO,
                    Message.MEDIA_AUDIO, Message.MEDIA_FILE):
        return explicit
    ct = (getattr(upload, 'content_type', '') or '').lower()
    if ct.startswith('image/'):
        return Message.MEDIA_IMAGE
    if ct.startswith('video/'):
        return Message.MEDIA_VIDEO
    if ct.startswith('audio/'):
        return Message.MEDIA_AUDIO
    return Message.MEDIA_FILE


# Max upload size: 25 MB per message media — keeps mobile uploads reasonable.
MAX_MEDIA_BYTES = 25 * 1024 * 1024


# ─── Messages within a conversation ───────────────────────────────────────────
@api_view(['GET', 'POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([IsAuthenticated])
def conversation_messages(request, conversation_id):
    try:
        conv = get_object_or_404(Conversation, id=conversation_id)
        if not conv.participants.filter(id=request.user.id).exists():
            return Response({'error': 'Not a participant'}, status=403)

        if request.method == 'GET':
            # Limit to last 500 to keep response small; client can paginate later.
            qs = conv.messages.select_related('sender', 'sender__profile').order_by('created_at')[:500]
            data = MessageSerializer(qs, many=True, context={'request': request}).data
            return Response(data)

        # POST: send a new message (text and/or media)
        text = (request.data.get('text') or '').strip()
        upload = request.FILES.get('media')

        if not text and not upload:
            return Response({'error': 'text or media is required'}, status=400)
        if text and len(text) > 4000:
            return Response({'error': 'text too long (max 4000 chars)'}, status=400)

        media_type = Message.MEDIA_TEXT
        media_name = ''
        media_size = None
        media_duration = None

        media_value = None
        if upload:
            if upload.size and upload.size > MAX_MEDIA_BYTES:
                return Response(
                    {'error': f'File too large (max {MAX_MEDIA_BYTES // (1024 * 1024)} MB)'},
                    status=400,
                )
            explicit_type = (request.data.get('media_type') or '').strip() or None
            media_type = _infer_media_type(upload, explicit_type)
            media_name = upload.name[:255] if upload.name else ''
            media_size = upload.size or None
            # Optional client-provided duration (for voice/video)
            dur_raw = request.data.get('media_duration')
            if dur_raw not in (None, ''):
                try:
                    media_duration = float(dur_raw)
                except (TypeError, ValueError):
                    media_duration = None

            # Create message without media first
            msg = Message.objects.create(
                conversation=conv,
                sender=request.user,
                text=text,
                media_type=media_type,
                media_name=media_name,
                media_size=media_size,
                media_duration=media_duration,
                delivery_status=Message.DELIVERY_SENT,
            )

            # ── Upload media (local filesystem only) ────────────────────────────
            from django.conf import settings as _settings
            import os
            media_root = _settings.MEDIA_ROOT
            messages_dir = os.path.join(media_root, 'messages')
            
            # Ensure directories exist
            for d in (media_root, messages_dir):
                if not os.path.exists(d):
                    try:
                        os.makedirs(d, exist_ok=True)
                        print(f'[messages] Created directory: {d}')
                    except Exception as e:
                        print(f'[messages] ERROR: mkdir {d} failed: {e}')
                        import traceback
                        traceback.print_exc()
                        msg.delete()
                        return Response(
                            {'error': f'Failed to create media directory: {str(e)}'},
                            status=500,
                        )
            
            # Check directory permissions
            if not os.access(messages_dir, os.W_OK):
                print(f'[messages] ERROR: No write permission for {messages_dir}')
                msg.delete()
                return Response(
                    {'error': 'Media directory is not writable'},
                    status=500,
                )
            
            try:
                upload.seek(0)
                msg.media.save(upload.name, upload)
                msg.save(update_fields=['media'])
                print(f'[messages] local FS saved: {msg.media.name}')
            except Exception as e:
                import traceback
                traceback.print_exc()
                msg.delete()
                return Response(
                    {'error': f'Failed to save media: {str(e)}'},
                    status=500,
                )
        else:
            # Create text-only message
            msg = Message.objects.create(
                conversation=conv,
                sender=request.user,
                text=text,
                media_type=Message.MEDIA_TEXT,
                delivery_status=Message.DELIVERY_SENT,
            )
        
        conv.last_message_at = timezone.now()
        conv.save(update_fields=['last_message_at'])

        # Sender has obviously read up to now
        MessageRead.objects.update_or_create(
            user=request.user, conversation=conv,
            defaults={'last_read_at': timezone.now()},
        )
        
        return Response(MessageSerializer(msg, context={'request': request}).data, status=201)
    except Exception as e:
        print(f'[conversation_messages] Error: {e}')
        import traceback
        traceback.print_exc()
        return Response({'error': 'Internal server error'}, status=500)


# ─── Edit / delete own message ────────────────────────────────────────────────
@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def edit_or_delete_message(request, message_id):
    msg = get_object_or_404(Message, id=message_id)
    if msg.sender_id != request.user.id:
        return Response({'error': 'Not your message'}, status=403)

    if request.method == 'DELETE':
        msg.is_deleted = True
        msg.text = ''
        msg.save(update_fields=['is_deleted', 'text'])
        return Response({'ok': True})

    # PATCH: edit text (only within 15-minute window)
    if not msg.is_editable:
        return Response({'error': 'Edit window has expired (15 minutes)'}, status=400)
    text = (request.data.get('text') or '').strip()
    if not text:
        return Response({'error': 'text is required'}, status=400)
    if len(text) > 4000:
        return Response({'error': 'text too long'}, status=400)
    msg.text = text
    msg.edited_at = timezone.now()
    msg.save(update_fields=['text', 'edited_at'])
    data = MessageSerializer(msg, context={'request': request}).data
    return Response(data)


# ─── Mark conversation as read ────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_conversation_read(request, conversation_id):
    conv = get_object_or_404(Conversation, id=conversation_id)
    if not conv.participants.filter(id=request.user.id).exists():
        return Response({'error': 'Not a participant'}, status=403)
    MessageRead.objects.update_or_create(
        user=request.user, conversation=conv,
        defaults={'last_read_at': timezone.now()},
    )
    return Response({'ok': True})


# ─── Unread DM badge count ────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unread_dm_count(request):
    """Total unread messages across all my conversations (for bottom-nav badge).

    Properly honours each conversation's MessageRead marker: a message is
    unread iff it was sent by someone else AND is newer than my last_read_at
    for that conversation (or I have no marker yet).  One SQL query.
    """
    try:
        my_read_at = MessageRead.objects.filter(
            conversation=OuterRef('conversation'),
            user=request.user,
        ).values('last_read_at')[:1]

        unread_count = (
            Message.objects
            .filter(conversation__participants=request.user)
            .exclude(sender=request.user)
            .annotate(_my_read_at=Subquery(my_read_at))
            .filter(Q(_my_read_at__isnull=True) | Q(created_at__gt=F('_my_read_at')))
            .count()
        )
        return Response({'unread_count': unread_count})
    except Exception as e:
        print(f'[unread_dm_count] Error: {e}')
        import traceback
        traceback.print_exc()
        return Response({'unread_count': 0})


# ─── User search (for "New Message") ──────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_users_for_dm(request):
    try:
        q = (request.GET.get('q') or '').strip()
        if not q:
            return Response([])
        users = (
            User.objects
            .filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
            .exclude(id=request.user.id)
            .select_related('profile')
            [:20]
        )
        return Response(BriefUserSerializer(users, many=True).data)
    except Exception as e:
        print(f'[search_users_for_dm] Error: {e}')
        return Response([])
