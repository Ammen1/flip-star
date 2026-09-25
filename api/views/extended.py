from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db.models import Count
from django.utils import timezone
from django.db import DatabaseError
from django.db import transaction as db_transaction
import re
from api.models import Comment, CommentLike, CommentReply, SavedPost, Reel, UserProfile, Mention
from api.serializers.extended import CommentSerializer, CommentLikeSerializer, CommentReplySerializer, SavedPostSerializer
from common.security import EncryptedPayloadMixin
from common.permissions import IsOwnerOrStaffOrReadOnly
from api.services.coin_purchase import insufficient_coins_payload

def parse_mentions(text, mentioner, comment=None, reply=None):
    """Parse @username mentions from text and create Mention records"""
    import re
    from django.contrib.auth.models import User
    from api.models import Block
    
    try:
        # Find all @username patterns
        pattern = r'@(\w+)'
        usernames = re.findall(pattern, text)
        
        # Get blocked users to exclude them
        blocked_ids = Block.objects.filter(blocker=mentioner).values_list('blocked_id', flat=True)
        
        created_mentions = []
        for username in usernames:
            try:
                mentioned_user = User.objects.get(username=username)
                
                # Skip if mentioning self, blocked user, or user who disabled mentions
                if mentioned_user.id == mentioner.id:
                    continue
                if mentioned_user.id in blocked_ids:
                    continue
                if not hasattr(mentioned_user, 'profile') or not mentioned_user.profile.allow_mentions:
                    continue
                
                # Create mention record
                mention = Mention.objects.create(
                    mentioned_user=mentioned_user,
                    comment=comment,
                    reply=reply,
                    mentioned_by=mentioner
                )
                created_mentions.append(mention)
                
                # Create notification for mentioned user
                from api.models import Notification, NotificationPreference
                # Respect notification preferences if present
                try:
                    prefs = mentioned_user.notification_prefs
                    if hasattr(prefs, 'mentions') and not prefs.mentions:
                        continue
                except NotificationPreference.DoesNotExist:
                    pass

                # Resolve associated reel (for deep linking from notifications)
                reel_obj = None
                if comment is not None:
                    reel_obj = getattr(comment, 'reel', None)
                elif reply is not None:
                    parent_comment = getattr(reply, 'comment', None)
                    if parent_comment is not None:
                        reel_obj = getattr(parent_comment, 'reel', None)

                snippet = (text or '')[:80]
                Notification.objects.create(
                    recipient=mentioned_user,
                    sender=mentioner,
                    notification_type='mention',
                    reel=reel_obj,
                    comment=comment,
                    message=f"@{mentioner.username} mentioned you: {snippet}"
                )
            except User.DoesNotExist:
                pass  # User doesn't exist, skip
            except Exception as e:
                print(f"[MENTIONS] Error creating mention for {username}: {e}")
                continue  # Continue with other mentions even if one fails
        
        return created_mentions
    except Exception as e:
        print(f"[MENTIONS] Error parsing mentions: {e}")
        return []  # Don't break comment/reply creation if mention parsing fails

class CommentViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer
    # Reads open to anyone; writes require auth, and any action not
    # explicitly narrowed by get_permissions() below (a future @action,
    # for instance) requires ownership or staff -- fails closed by default.
    permission_classes = [IsOwnerOrStaffOrReadOnly]
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'like', 'reply']:
            self.permission_classes = [IsAuthenticated]
        return super().get_permissions()
    
    def get_queryset(self):
        try:
            queryset = Comment.objects.all()
            reel_id = self.request.query_params.get('reel')
            if reel_id:
                queryset = queryset.filter(reel_id=reel_id)
            return queryset
        except DatabaseError as e:
            # Handle missing database columns gracefully
            if 'does not exist' in str(e) or 'column' in str(e).lower():
                # Return empty queryset if database schema is not updated
                return Comment.objects.none()
            raise
    
    def create(self, request, *args, **kwargs):
        """Commenting is subscriber-only, and costs what a comment costs.

        This viewset is a second way in to the same Comment row the reel's
        own `comments` action writes. That action gates and charges; this
        one did neither, so a non-subscriber could comment here for free
        and a subscriber could comment without paying. The gate was added
        first; the charge is here.

        Both routes now go through `charge_engagement`, which is the only
        thing that knows the price -- so the two cannot drift apart again
        the way they did. See the note in
        api/services/subscription_access.py on why coins are not the gate.
        """
        from api.services.campaign_charges import InsufficientCoins
        from api.services.subscription_access import subscriber_action_refusal

        refusal = subscriber_action_refusal(request.user, 'comment')
        if refusal is not None:
            return Response(refusal, status=status.HTTP_403_FORBIDDEN)

        # The comment and its charge commit together. The reel action
        # learned this the hard way: charging outside a transaction left
        # users paying for comments that were never written.
        try:
            with db_transaction.atomic():
                return super().create(request, *args, **kwargs)
        except InsufficientCoins as exc:
            return Response(
                insufficient_coins_payload(exc.required, exc.available, message=exc.message),
                status=status.HTTP_400_BAD_REQUEST,
            )

    def perform_create(self, serializer):
        from api.services.campaign_charges import charge_engagement

        try:
            comment = serializer.save(user=self.request.user)
            # Parse mentions from comment text
            parse_mentions(comment.text, self.request.user, comment=comment)
        except DatabaseError as e:
            if 'does not exist' in str(e) or 'column' in str(e).lower():
                # Handle missing fields by setting default values
                comment = serializer.save(user=self.request.user, edited_at=None, is_deleted=False)
                # Parse mentions from comment text
                parse_mentions(comment.text, self.request.user, comment=comment)
            else:
                raise

        # After the row exists, inside create()'s transaction. Raises
        # InsufficientCoins, which create() turns into a 400 and which
        # rolls the comment back -- an unpaid comment is not written.
        if comment.reel_id:
            charge_engagement(self.request.user, comment.reel, 'comment')
    
    def update(self, request, *args, **kwargs):
        comment = self.get_object()
        # Only allow editing own comments
        if comment.user != request.user:
            return Response({'error': 'You can only edit your own comments'}, status=status.HTTP_403_FORBIDDEN)
        # No time-based edit window — owners may edit their comments at any time.
        if comment.is_deleted:
            return Response({'error': 'Cannot edit a deleted comment'}, status=status.HTTP_400_BAD_REQUEST)

        text = request.data.get('text', '').strip()
        if not text:
            return Response({'error': 'Text is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        comment.text = text
        try:
            comment.edited_at = timezone.now()
        except DatabaseError:
            # If edited_at field doesn't exist, skip it
            pass
        comment.save()
        
        serializer = self.get_serializer(comment)
        return Response(serializer.data)
    
    def destroy(self, request, *args, **kwargs):
        comment = self.get_object()
        # Only allow deleting own comments
        if comment.user != request.user:
            return Response({'error': 'You can only delete your own comments'}, status=status.HTTP_403_FORBIDDEN)
        
        # Soft delete
        try:
            comment.is_deleted = True
        except DatabaseError:
            # If is_deleted field doesn't exist, hard delete
            comment.delete()
            return Response({'ok': True})
        comment.text = ''
        comment.save()
        return Response({'ok': True})
    
    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        comment = self.get_object()
        like, created = CommentLike.objects.get_or_create(
            user=request.user,
            comment=comment
        )
        if not created:
            like.delete()
            return Response({'liked': False, 'likes_count': comment.likes_count})
        return Response({'liked': True, 'likes_count': comment.likes_count})
    
    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        comment = self.get_object()
        text = request.data.get('text')
        if not text:
            return Response({'error': 'Text is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            reply = CommentReply.objects.create(
                user=request.user,
                comment=comment,
                text=text
            )
        except DatabaseError as e:
            if 'does not exist' in str(e) or 'column' in str(e).lower():
                # Handle missing fields by setting default values
                reply = CommentReply.objects.create(
                    user=request.user,
                    comment=comment,
                    text=text,
                    edited_at=None,
                    is_deleted=False
                )
            else:
                raise
        
        # Parse mentions from reply text
        parse_mentions(reply.text, request.user, reply=reply)
        
        serializer = CommentReplySerializer(reply)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class CommentReplyViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
    queryset = CommentReply.objects.all()
    serializer_class = CommentReplySerializer
    # Reads open to anyone; writes require auth, and any action not
    # explicitly narrowed by get_permissions() below requires ownership or
    # staff -- fails closed by default.
    permission_classes = [IsOwnerOrStaffOrReadOnly]
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'like']:
            self.permission_classes = [IsAuthenticated]
        return super().get_permissions()
    
    def create(self, request, *args, **kwargs):
        """Replying to a comment is subscriber-only.

        This viewset is a second way in: the reel's own `comments` action
        gates and charges, and these routes did neither -- a non-subscriber
        could reply here for free. See the note in
        api/services/subscription_access.py on why coins are not the gate.
        """
        from api.services.subscription_access import subscriber_action_refusal

        refusal = subscriber_action_refusal(request.user, 'comment')
        if refusal is not None:
            return Response(refusal, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        reply = serializer.save(user=self.request.user)
        # Parse mentions from reply text
        parse_mentions(reply.text, self.request.user, reply=reply)
    
    def update(self, request, *args, **kwargs):
        reply = self.get_object()
        # Only allow editing own replies
        if reply.user != request.user:
            return Response({'error': 'You can only edit your own replies'}, status=status.HTTP_403_FORBIDDEN)
        # No time-based edit window — owners may edit their replies at any time.
        if reply.is_deleted:
            return Response({'error': 'Cannot edit a deleted reply'}, status=status.HTTP_400_BAD_REQUEST)

        text = request.data.get('text', '').strip()
        if not text:
            return Response({'error': 'Text is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        reply.text = text
        reply.edited_at = timezone.now()
        reply.save()
        
        serializer = self.get_serializer(reply)
        return Response(serializer.data)
    
    def destroy(self, request, *args, **kwargs):
        reply = self.get_object()
        # Only allow deleting own replies
        if reply.user != request.user:
            return Response({'error': 'You can only delete your own replies'}, status=status.HTTP_403_FORBIDDEN)
        
        # Soft delete
        reply.is_deleted = True
        reply.text = ''
        reply.save()
        return Response({'ok': True})
    
    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        try:
            reply = self.get_object()
            like, created = CommentLike.objects.get_or_create(
                user=request.user,
                reply=reply
            )
            if not created:
                like.delete()
                return Response({'liked': False, 'likes_count': reply.likes_count})
            return Response({'liked': True, 'likes_count': reply.likes_count})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=500)

class SavedPostViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
    serializer_class = SavedPostSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return SavedPost.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def toggle(self, request):
        reel_id = request.data.get('reel_id')
        if not reel_id:
            return Response({'error': 'reel_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        reel = get_object_or_404(Reel, id=reel_id)
        saved, created = SavedPost.objects.get_or_create(
            user=request.user,
            reel=reel
        )
        
        if not created:
            saved.delete()
            return Response({'saved': False})
        return Response({'saved': True})

class ProfilePhotoViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def upload(self, request):
        profile = request.user.profile
        photo = request.FILES.get('photo')
        
        if not photo:
            return Response({'error': 'Photo is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        profile.profile_photo = photo
        profile.save()
        
        return Response({
            'profile_photo': profile.profile_photo.url if profile.profile_photo else None
        })
