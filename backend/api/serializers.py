from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, Reel, Comment, CommentLike, CommentReply, SavedPost, Vote, Quest, UserQuest, Subscription, NotificationPreference, Competition, Winner, Follow, Report, Notification, Block


def build_feed_context(request):
    """Return a serializer context pre-populated with lookups shared across
    all feed entries.  Call this anywhere ReelSerializer is used in a list
    context to turn per-reel N+1 queries into O(1) lookups.
    """
    ctx = {'request': request}
    if request and getattr(request, 'user', None) and request.user.is_authenticated:
        try:
            ctx['followed_user_ids'] = set(
                Follow.objects.filter(follower=request.user)
                .values_list('following_id', flat=True)
            )
        except Exception:
            ctx['followed_user_ids'] = set()
    else:
        ctx['followed_user_ids'] = set()
    return ctx

class UserSerializer(serializers.ModelSerializer):
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    profile_photo = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'followers_count', 'following_count', 'profile_photo', 'bio', 'is_following']
    
    def get_followers_count(self, obj):
        # Use prefetched count if available
        if hasattr(obj, '_prefetched_followers_count'):
            return obj._prefetched_followers_count
        return obj.followers.count()
    
    def get_following_count(self, obj):
        if hasattr(obj, '_prefetched_following_count'):
            return obj._prefetched_following_count
        return obj.following.count()
    
    def get_profile_photo(self, obj):
        try:
            profile = obj.profile
            if profile and profile.profile_photo:
                return profile.profile_photo.url
        except UserProfile.DoesNotExist:
            pass
        return None
    
    def get_bio(self, obj):
        try:
            return obj.profile.bio
        except UserProfile.DoesNotExist:
            return ''
    
    def get_is_following(self, obj):
        request = self.context.get('request')
        if not (request and request.user.is_authenticated):
            return False
        # Fast path: the view pre-computed the set of followed IDs in one
        # query and stashed it in context — avoids N+1 in any list endpoint.
        followed = self.context.get('followed_user_ids')
        if followed is not None:
            return obj.id in followed
        return Follow.objects.filter(follower=request.user, following=obj).exists()


class FeedUserSerializer(serializers.ModelSerializer):
    """Lightweight user shape for embedding in feeds.

    Skips follower/following counts (not used per-post in the UI) to avoid
    two extra DB queries per reel.  `is_following` still resolves in O(1)
    from `context['followed_user_ids']` set by the view.
    """
    profile_photo = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'full_name', 'profile_photo', 'is_following']

    def get_full_name(self, obj):
        # Avoid calling obj.get_full_name() which accesses fields individually
        fn = (obj.first_name or '').strip()
        ln = (obj.last_name or '').strip()
        return (fn + ' ' + ln).strip() or obj.username

    def get_profile_photo(self, obj):
        # obj.profile is prefetched via select_related('user__profile')
        try:
            pf = obj.profile.profile_photo
            if pf and pf.name:
                return pf.name if pf.name.startswith('http') else pf.url
        except Exception:
            pass
        return None

    def get_is_following(self, obj):
        request = self.context.get('request')
        if not (request and request.user.is_authenticated):
            return False
        followed = self.context.get('followed_user_ids')
        if followed is not None:
            return obj.id in followed
        return Follow.objects.filter(follower=request.user, following=obj).exists()

class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'username', 'profile_photo', 'bio', 'xp', 'level', 'streak', 'last_checkin',
                  'coins', 'coins_earned_total', 'coins_spent_total',
                  'points', 'points_earned_total', 'points_withdrawn_total',
                  'login_streak', 'last_login_date', 'longest_login_streak', 'phone_number']

class ReelSerializer(serializers.ModelSerializer):
    # FeedUserSerializer is intentionally used here — it skips the per-user
    # follower/following counts (not shown per-post) so a 10-reel feed no
    # longer fires 30+ count() queries.
    user = FeedUserSerializer(read_only=True)
    comment_count = serializers.SerializerMethodField()
    hashtags_list = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    recent_comments = serializers.SerializerMethodField()
    votes = serializers.SerializerMethodField()  # Calculate dynamically from Vote table
    gift_count = serializers.SerializerMethodField()  # Count of gifts received
    campaign_id = serializers.PrimaryKeyRelatedField(source='campaign', read_only=True)
    campaign_title = serializers.CharField(source='campaign.title', read_only=True, default=None)

    thumbnail = serializers.SerializerMethodField()
    blurhash = serializers.CharField(read_only=True)
    duration = serializers.FloatField(read_only=True)
    processed = serializers.BooleanField(read_only=True)

    class Meta:
        model = Reel
        fields = ['id', 'user', 'image', 'media', 'thumbnail', 'blurhash', 'duration', 'processed', 'caption', 'hashtags', 'hashtags_list', 'overlay_text', 'votes', 'view_count', 'comment_count', 'shares', 'gift_count', 'created_at', 'is_liked', 'is_saved', 'recent_comments', 'is_campaign_post', 'campaign_id', 'campaign_title']
    
    def _build_url(self, field, request):
        """Build absolute URL for a file field, handling both local and Cloudinary storage."""
        try:
            if not field:
                return None
            name = field.name if hasattr(field, 'name') else str(field)
            if not name:
                return None

            # Already a full URL (stored via raw SQL after Cloudinary upload) — return as-is
            if name.startswith('http://') or name.startswith('https://'):
                return name

            # Properly rooted local path (e.g. /media/reels/fallback_5.webm)
            if name.startswith('/'):
                if request:
                    return request.build_absolute_uri(name)
                from django.conf import settings
                base = getattr(settings, 'BACKEND_URL', 'https://postworq.onrender.com')
                return f"{base}{name}"

            # Only paths we intentionally write as relative Django media paths
            # are valid (e.g. reels/fallback_5.webm from our local fallback code).
            # Legacy entries like "media/rec_*.webm" or any other relative path would
            # make the Cloudinary storage backend generate a phantom URL → 404.
            if not name.startswith('reels/'):
                return None

            # Known-good relative path — let Django storage resolve it
            url = field.url
            if not url:
                return None
            if url.startswith('http://') or url.startswith('https://'):
                return url
            if request:
                return request.build_absolute_uri(url)
            from django.conf import settings
            base = getattr(settings, 'BACKEND_URL', 'https://postworq.onrender.com')
            return f"{base}{url}"
        except Exception:
            return None

    def get_image(self, obj):
        return self._build_url(obj.image, self.context.get('request'))

    def get_media(self, obj):
        return self._build_url(obj.media, self.context.get('request'))

    def get_thumbnail(self, obj):
        return self._build_url(obj.thumbnail, self.context.get('request'))
    
    def get_comment_count(self, obj):
        # Always use actual count to ensure accuracy
        try:
            return obj.comments.count()
        except:
            return 0
    
    def get_hashtags_list(self, obj):
        return obj.get_hashtags_list()
    
    def get_is_liked(self, obj):
        # Use DB annotation if available (set by ReelViewSet.get_queryset)
        if hasattr(obj, 'is_liked_db'):
            return obj.is_liked_db
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            from .models import Vote
            return Vote.objects.filter(user=request.user, reel=obj).exists()
        return False
    
    def get_votes(self, obj):
        # Use DB annotation if available (set by ReelViewSet.get_queryset)
        if hasattr(obj, 'votes_count_db'):
            return obj.votes_count_db
        # Fallback to separate query only when annotation not available
        from .models import Vote
        return Vote.objects.filter(reel=obj).count()
    
    def get_gift_count(self, obj):
        # Use DB annotation if available (set by ReelViewSet.get_queryset)
        if hasattr(obj, 'gift_count_db'):
            return obj.gift_count_db
        # Fallback to counting gifts_received
        return obj.gifts_received.count()
    
    def get_is_saved(self, obj):
        # Use DB annotation if available (set by ReelViewSet.get_queryset)
        if hasattr(obj, 'is_saved_db'):
            return obj.is_saved_db
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            from .models import SavedPost
            return SavedPost.objects.filter(user=request.user, reel=obj).exists()
        return False
    
    def get_recent_comments(self, obj):
        # Use prefetched comments if available (set by ReelViewSet.get_queryset with prefetch_related)
        if hasattr(obj, 'prefetched_comments'):
            comments = list(obj.prefetched_comments)[:3]
            return CommentSerializer(comments, many=True).data
        # Fallback to query only when prefetch not available
        from .models import Comment
        recent_comments = Comment.objects.filter(reel=obj).select_related('user').order_by('-created_at')[:3]
        return CommentSerializer(recent_comments, many=True).data

class CommentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Comment
        fields = ['id', 'user', 'reel', 'text', 'created_at']

class CommentLikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommentLike
        fields = ['id', 'user', 'comment', 'created_at']

class CommentReplySerializer(serializers.ModelSerializer):
    class Meta:
        model = CommentReply
        fields = ['id', 'user', 'comment', 'text', 'created_at', 'edited_at', 'is_deleted']
        read_only_fields = ['created_at', 'edited_at', 'is_deleted']

class SavedPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedPost
        fields = ['id', 'user', 'reel', 'created_at']

class VoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vote
        fields = ['id', 'user', 'reel', 'created_at']

class QuestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quest
        fields = ['id', 'title', 'description', 'xp_reward', 'is_active']

class UserQuestSerializer(serializers.ModelSerializer):
    quest = QuestSerializer(read_only=True)
    
    class Meta:
        model = UserQuest
        fields = ['id', 'quest', 'completed', 'completed_at']

class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ['id', 'plan', 'started_at', 'expires_at']

class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ['id', 'email_notifications', 'push_notifications', 'sms_notifications', 'phone', 'likes', 'comments', 'follows', 'messages']

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'first_name', 'last_name']
    
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        # Signals will handle profile creation
        return user

class CompetitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Competition
        fields = ['id', 'title', 'description', 'start_date', 'end_date', 'prize', 'is_active', 'created_at']

class WinnerSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    competition = CompetitionSerializer(read_only=True)
    reel = ReelSerializer(read_only=True)
    
    class Meta:
        model = Winner
        fields = ['id', 'competition', 'user', 'reel', 'votes_received', 'prize_claimed', 'announced_at']

class FollowSerializer(serializers.ModelSerializer):
    follower = UserSerializer(read_only=True)
    following = UserSerializer(read_only=True)
    
    class Meta:
        model = Follow
        fields = ['id', 'follower', 'following', 'created_at']

class BlockSerializer(serializers.ModelSerializer):
    blocker = UserSerializer(read_only=True)
    blocked = UserSerializer(read_only=True)
    
    class Meta:
        model = Block
        fields = ['id', 'blocker', 'blocked', 'created_at']

class ReportSerializer(serializers.ModelSerializer):
    reported_by = UserSerializer(read_only=True)
    reported_user = UserSerializer(read_only=True)
    reported_reel = ReelSerializer(read_only=True)
    reviewed_by = UserSerializer(read_only=True)
    # Write-only FK fields so frontend can submit IDs
    reported_user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='reported_user', write_only=True, required=False, allow_null=True
    )
    reported_reel_id = serializers.PrimaryKeyRelatedField(
        queryset=Reel.objects.all(), source='reported_reel', write_only=True, required=False, allow_null=True
    )
    reported_comment_id = serializers.PrimaryKeyRelatedField(
        queryset=Comment.objects.all(), source='reported_comment', write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = Report
        fields = [
            'id', 'reported_by',
            'reported_user', 'reported_user_id',
            'reported_reel', 'reported_reel_id',
            'reported_comment_id',
            'target_type', 'report_type', 'description',
            'status', 'priority',
            'resolution_notes', 'reviewed_by',
            'created_at', 'updated_at', 'resolved_at',
        ]


class NotificationSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    reel = ReelSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'sender', 'notification_type', 'reel', 'comment', 'message', 'is_read', 'created_at']
        read_only_fields = ['id', 'created_at']
