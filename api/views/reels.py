from django.db.models import Count, Exists, OuterRef, Prefetch
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models import Comment, Follow, Reel, SavedPost, Vote
from api.serializers.core import ReelSerializer, build_feed_context
from common.security import encrypted_endpoint


def _annotated_reels(user):
    """Shared optimized queryset: select_related + prefetched comments +
    DB-side comment_count / vote_count / is_liked / is_saved annotations.
    Matches what ReelViewSet.get_queryset does so the serializer never
    falls into per-object query fallbacks.
    """
    recent_comments_prefetch = Prefetch(
        'comments',
        queryset=Comment.objects.select_related('user').order_by('-created_at')[:10],
        to_attr='prefetched_comments',
    )
    qs = (
        Reel.objects.select_related('user', 'user__profile')
        .prefetch_related(recent_comments_prefetch)
        .annotate(
            comment_count_db=Count('comments', distinct=True),
            votes_count_db=Count('reel_votes', distinct=True),
        )
    )
    if user and user.is_authenticated:
        qs = qs.annotate(
            is_liked_db=Exists(Vote.objects.filter(user=user, reel=OuterRef('pk'))),
            is_saved_db=Exists(SavedPost.objects.filter(user=user, reel=OuterRef('pk'))),
        )
    return qs


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def reels_following(request):
    """Get reels from users that the current user follows"""
    user = request.user
    if not user or not user.is_authenticated:
        return Response([])

    following_users = Follow.objects.filter(follower=user).values_list('following_id', flat=True)

    reels = _annotated_reels(user).filter(user_id__in=following_users).order_by('-created_at')

    from api.models import NotInterested

    not_interested_ids = NotInterested.objects.filter(user=user).values_list('reel_id', flat=True)
    reels = reels.exclude(id__in=not_interested_ids)

    # Cap to a sane upper bound so a power-follower isn't punished with
    # a multi-MB response + serializer CPU burn on every poll.
    reels = reels[:50]
    serializer = ReelSerializer(reels, many=True, context=build_feed_context(request))
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def reels_saved(request):
    """Get saved/bookmarked reels for the current user"""
    user = request.user
    saved_reel_ids = SavedPost.objects.filter(user=user).values_list('reel_id', flat=True)
    reels = _annotated_reels(user).filter(id__in=saved_reel_ids).order_by('-created_at')[:100]
    serializer = ReelSerializer(reels, many=True, context=build_feed_context(request))
    return Response(serializer.data)


@api_view(['GET'])
@encrypted_endpoint
def reels_trending(request):
    """Get trending/popular reels based on votes and comments"""
    from datetime import timedelta

    from django.utils import timezone

    week_ago = timezone.now() - timedelta(days=7)

    reels = (
        _annotated_reels(request.user)
        .filter(created_at__gte=week_ago)
        .annotate(engagement=Count('reel_votes') + Count('comments'))
        .order_by('-engagement', '-created_at')
    )

    # Optional ?category=<slug>. Absent or "all" leaves the feed untouched, so
    # existing callers keep their current behaviour. An unknown slug returns
    # 400 rather than silently serving an unfiltered feed, which would look
    # like the filter was applied and simply matched everything.
    category_slug = (request.GET.get('category') or '').strip()
    if category_slug and category_slug != 'all':
        from api.models import Category

        category = Category.objects.filter(slug=category_slug, is_active=True).first()
        if category is None:
            return Response(
                {
                    'error': 'Unknown or inactive category.',
                    'code': 'invalid_category',
                    'category': category_slug,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        reels = reels.filter(category=category)

    if request.user.is_authenticated:
        from api.models import NotInterested

        not_interested_ids = NotInterested.objects.filter(user=request.user).values_list(
            'reel_id', flat=True
        )
        reels = reels.exclude(id__in=not_interested_ids)

    reels = reels[:50]
    serializer = ReelSerializer(reels, many=True, context=build_feed_context(request))
    return Response(serializer.data)
