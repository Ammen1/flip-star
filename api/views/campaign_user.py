from datetime import datetime, timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.models import Comment, Reel, User, Vote
from api.models.campaign import Campaign
from api.models.campaign_extended import (
    CampaignBadge,
    CampaignTheme,
    PostScore,
    UserCampaignStats,
)
from common.security import encrypted_endpoint

# ==================== CAMPAIGN DISCOVERY ====================


@api_view(['GET'])
@permission_classes([AllowAny])
@encrypted_endpoint
def get_active_campaigns(request):
    """Get all active campaigns"""
    now = timezone.now()
    campaigns = Campaign.objects.filter(
        status='active', start_date__lte=now, entry_deadline__gte=now
    )

    data = []
    for campaign in campaigns:
        # Get active theme
        active_theme = campaign.themes.filter(is_active=True).first()

        # Check if user has joined
        user_stats = (
            UserCampaignStats.objects.filter(user=request.user, campaign=campaign).first()
            if request.user.is_authenticated
            else None
        )

        data.append(
            {
                'id': campaign.id,
                'title': campaign.title,
                'description': campaign.description,
                'image': campaign.image.url if campaign.image else None,
                'prize_value': str(campaign.prize_value),
                'start_date': campaign.start_date,
                'entry_deadline': campaign.entry_deadline,
                'total_entries': campaign.total_entries,
                'active_theme': {
                    'id': active_theme.id,
                    'title': active_theme.title,
                    'description': active_theme.description,
                    'week_number': active_theme.week_number,
                    'end_date': active_theme.end_date,
                }
                if active_theme
                else None,
                'user_joined': user_stats is not None,
                'user_posts': user_stats.approved_posts if user_stats else 0,
                'user_rank': user_stats.overall_rank if user_stats else None,
            }
        )

    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
@encrypted_endpoint
def get_campaign_detail_extended(request, campaign_id):
    """Get detailed campaign information including themes and user stats"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)

    # Get themes
    themes = campaign.themes.all()
    themes_data = [
        {
            'id': theme.id,
            'title': theme.title,
            'description': theme.description,
            'week_number': theme.week_number,
            'start_date': theme.start_date,
            'end_date': theme.end_date,
            'is_active': theme.is_active,
            'posts_count': theme.theme_posts.filter(is_campaign_post=True).count(),
        }
        for theme in themes
    ]

    # Get user stats
    user_stats = (
        UserCampaignStats.objects.filter(user=request.user, campaign=campaign).first()
        if request.user.is_authenticated
        else None
    )

    # Get user's posts in this campaign
    user_posts = (
        PostScore.objects.filter(user=request.user, campaign=campaign).select_related(
            'reel', 'theme'
        )
        if request.user.is_authenticated
        else []
    )

    user_posts_data = [
        {
            'id': score.id,
            'reel_id': score.reel.id,
            'theme': {
                'id': score.theme.id,
                'title': score.theme.title,
            }
            if score.theme
            else None,
            'moderation_status': score.moderation_status,
            'total_score': float(score.total_score),
            'created_at': score.created_at,
        }
        for score in user_posts
    ]

    return Response(
        {
            'campaign': {
                'id': campaign.id,
                'title': campaign.title,
                'description': campaign.description,
                'image': campaign.image.url if campaign.image else None,
                'prize_title': campaign.prize_title,
                'prize_value': str(campaign.prize_value),
                'status': campaign.status,
                'start_date': campaign.start_date,
                'entry_deadline': campaign.entry_deadline,
                'total_entries': campaign.total_entries,
                'min_followers': campaign.min_followers,
                'min_level': campaign.min_level,
                'required_hashtags': campaign.required_hashtags,
            },
            'themes': themes_data,
            'user_stats': {
                'total_posts': user_stats.total_posts if user_stats else 0,
                'approved_posts': user_stats.approved_posts if user_stats else 0,
                'total_score': float(user_stats.total_score) if user_stats else 0,
                'overall_rank': user_stats.overall_rank if user_stats else None,
                'daily_rank': user_stats.daily_rank if user_stats else None,
                'weekly_rank': user_stats.weekly_rank if user_stats else None,
                'current_streak': user_stats.current_streak if user_stats else 0,
            }
            if user_stats
            else None,
            'user_posts': user_posts_data,
        }
    )


# ==================== POST CREATION ====================


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_campaign_post(request):
    """Create a post for a campaign"""
    campaign_id = request.data.get('campaign_id')
    theme_id = request.data.get('theme_id')

    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)

    # Check if campaign is active
    if not campaign.is_active():
        return Response(
            {'error': 'Campaign is not accepting entries'}, status=status.HTTP_400_BAD_REQUEST
        )

    # Get theme
    theme = None
    if theme_id:
        try:
            theme = CampaignTheme.objects.get(id=theme_id, campaign=campaign)
        except CampaignTheme.DoesNotExist:
            return Response({'error': 'Theme not found'}, status=status.HTTP_404_NOT_FOUND)
    else:
        # Auto-assign active theme
        theme = campaign.themes.filter(is_active=True).first()

    # Create the reel
    caption = request.data.get('caption', '')
    hashtags = request.data.get('hashtags', '')

    # Handle file upload
    media_file = request.FILES.get('media')
    image_file = request.FILES.get('image')

    if not media_file and not image_file:
        return Response({'error': 'No media file provided'}, status=status.HTTP_400_BAD_REQUEST)

    # Generate thumbnail if video is uploaded without image
    thumbnail_file = image_file
    if media_file and not image_file:
        import os
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile

        is_video = media_file.content_type.startswith('video/') or media_file.name.lower().endswith(
            ('.mp4', '.webm', '.mov', '.avi', '.mkv')
        )

        if is_video:
            try:
                # Save uploaded video to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_video:
                    for chunk in media_file.chunks():
                        temp_video.write(chunk)
                    temp_video_path = temp_video.name

                # Generate thumbnail using ffmpeg
                thumbnail_path = temp_video_path.replace('.mp4', '_thumb.jpg')
                import ffmpeg

                (
                    ffmpeg.input(temp_video_path, ss='00:00:01')  # Capture frame at 1 second
                    .output(thumbnail_path, vframes=1, format='image2', vcodec='mjpeg')
                    .overwrite_output()
                    .run(quiet=True)
                )

                # Read thumbnail and create Django file
                with open(thumbnail_path, 'rb') as thumb_file:
                    thumbnail_file = SimpleUploadedFile(
                        name=f"{media_file.name.rsplit('.', 1)[0]}_thumb.jpg",
                        content=thumb_file.read(),
                        content_type='image/jpeg',
                    )

                # Clean up temp files
                os.unlink(temp_video_path)
                if os.path.exists(thumbnail_path):
                    os.unlink(thumbnail_path)
            except Exception as e:
                print(f'[CAMPAIGN_POST] Thumbnail generation failed: {e}')
                # Continue without thumbnail if generation fails

    reel = Reel.objects.create(
        user=request.user,
        caption=caption,
        hashtags=hashtags,
        media=media_file,
        image=thumbnail_file,
        campaign=campaign,
        theme=theme,
        is_campaign_post=True,
    )

    # Create post score entry for moderation
    post_score = PostScore.objects.create(
        reel=reel, campaign=campaign, theme=theme, user=request.user, moderation_status='pending'
    )

    # Update or create user stats
    stats, created = UserCampaignStats.objects.get_or_create(user=request.user, campaign=campaign)

    # Update streak (use local date so day boundaries match user's timezone)
    today = timezone.localdate()
    if stats.last_post_date:
        days_diff = (today - stats.last_post_date).days
        if days_diff == 0:
            # Already posted today — keep streak as-is
            pass
        elif days_diff == 1:
            stats.current_streak += 1
        elif days_diff > 1:
            stats.current_streak = 1
    else:
        stats.current_streak = 1

    stats.longest_streak = max(stats.longest_streak, stats.current_streak)
    stats.last_post_date = today

    # Count distinct local-calendar days the user actually posted in this campaign
    post_dates = PostScore.objects.filter(
        user=request.user,
        campaign=campaign,
    ).values_list('created_at', flat=True)
    unique_days = {timezone.localtime(ts).date() for ts in post_dates if ts}
    unique_days.add(today)  # include the post we just created
    stats.days_participated = len(unique_days)
    stats.save()

    return Response(
        {
            'message': 'Campaign post created and submitted for moderation',
            'reel_id': reel.id,
            'post_score_id': post_score.id,
            'moderation_status': 'pending',
        },
        status=status.HTTP_201_CREATED,
    )


# ==================== CAMPAIGN FEED ====================


@api_view(['GET'])
@permission_classes([AllowAny])
@encrypted_endpoint
def get_campaign_feed(request, campaign_id):
    """Get feed of approved campaign posts"""
    print(f'[CAMPAIGN FEED] Request for campaign {campaign_id}')
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        print(f'[CAMPAIGN FEED] Campaign: {campaign.title}')
    except Campaign.DoesNotExist:
        print(f'[CAMPAIGN FEED] Campaign {campaign_id} not found')
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)

    # Accept both 'filter' (frontend) and 'sort' (legacy) params
    filter_param = request.query_params.get('filter', request.query_params.get('sort', 'all'))
    theme_id = request.query_params.get('theme')
    print(f'[CAMPAIGN FEED] Filter: {filter_param}, Theme: {theme_id}')

    # Base query - approved posts only
    posts = PostScore.objects.filter(
        campaign=campaign, moderation_status='approved'
    ).select_related('user', 'reel', 'theme')

    print(f'[CAMPAIGN FEED] Total approved posts: {posts.count()}')

    # Filter by theme if specified
    if theme_id:
        posts = posts.filter(theme_id=theme_id)
        print(f'[CAMPAIGN FEED] After theme filter: {posts.count()}')

    # Sort: frontend sends all/top/recent; legacy sends trending/top/latest
    if filter_param in ('top',):
        posts = posts.order_by('-total_score')
    elif filter_param in ('recent', 'latest'):
        posts = posts.order_by('-created_at')
    else:  # 'all' or 'trending'
        posts = posts.order_by('-total_score', '-created_at')

    # Paginate
    page_size = 20
    posts = posts[:page_size]
    print(f'[CAMPAIGN FEED] Returning {len(posts)} posts')

    data = []
    for post in posts:
        # Get engagement counts
        likes_count = Vote.objects.filter(reel=post.reel).count()
        comments_count = Comment.objects.filter(reel=post.reel).count()

        # Check if current user liked
        user_liked = (
            Vote.objects.filter(reel=post.reel, user=request.user).exists()
            if request.user.is_authenticated
            else False
        )

        def _abs_url(field):
            if not field or not field.name:
                return None
            try:
                url = field.url
                if not url:
                    return None
                if url.startswith('http'):
                    return url
                return request.build_absolute_uri(url)
            except Exception:
                return None

        image_url = _abs_url(post.reel.image)
        media_url = _abs_url(post.reel.media)
        thumbnail_url = _abs_url(post.reel.thumbnail)

        print(
            f'[CAMPAIGN FEED] Post {post.id}: image={image_url}, media={media_url}, thumbnail={thumbnail_url}, user={post.user.username}'
        )

        data.append(
            {
                'id': post.id,
                'reel': {
                    'id': post.reel.id,
                    'caption': post.reel.caption,
                    'hashtags': post.reel.hashtags,
                    'image': image_url,
                    'media': media_url,
                    'thumbnail': thumbnail_url
                    or image_url,  # Use thumbnail if available, fallback to image
                    'created_at': post.reel.created_at,
                },
                'user': {
                    'id': post.user.id,
                    'username': post.user.username,
                },
                'theme': {
                    'id': post.theme.id,
                    'title': post.theme.title,
                    'week_number': post.theme.week_number,
                }
                if post.theme
                else None,
                'scores': {
                    'total': float(post.total_score),
                    'creativity': float(post.creativity_score),
                    'engagement': float(post.engagement_score),
                    'quality': float(post.quality_score),
                    'theme_relevance': float(post.theme_relevance_score),
                },
                'engagement': {
                    'likes': likes_count,
                    'comments': comments_count,
                    'user_liked': user_liked,
                },
            }
        )

    print(f'[CAMPAIGN FEED] Response: {len(data)} posts')
    return Response({'posts': data})


# ==================== USER PROFILE CAMPAIGN STATS ====================


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_user_campaign_profile(request, user_id=None):
    """Get user's campaign participation and achievements"""
    if user_id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    else:
        user = request.user

    # Get all campaign stats
    stats = UserCampaignStats.objects.filter(user=user).select_related('campaign')

    campaigns_data = []
    for stat in stats:
        campaigns_data.append(
            {
                'campaign': {
                    'id': stat.campaign.id,
                    'title': stat.campaign.title,
                    'status': stat.campaign.status,
                },
                'stats': {
                    'total_posts': stat.total_posts,
                    'approved_posts': stat.approved_posts,
                    'total_score': float(stat.total_score),
                    'average_score': float(stat.average_score),
                    'overall_rank': stat.overall_rank,
                    'current_streak': stat.current_streak,
                    'longest_streak': stat.longest_streak,
                },
            }
        )

    # Get badges
    badges = CampaignBadge.objects.filter(user=user).select_related('campaign')
    badges_data = [
        {
            'id': badge.id,
            'badge_type': badge.badge_type,
            'title': badge.title,
            'description': badge.description,
            'icon': badge.icon,
            'campaign': {
                'id': badge.campaign.id,
                'title': badge.campaign.title,
            },
            'earned_at': badge.earned_at,
        }
        for badge in badges
    ]

    # Get total wins
    from api.models.campaign_extended import SelectedWinner

    total_wins = SelectedWinner.objects.filter(user=user).count()

    return Response(
        {
            'user': {
                'id': user.id,
                'username': user.username,
            },
            'campaigns': campaigns_data,
            'badges': badges_data,
            'total_campaigns': stats.count(),
            'total_wins': total_wins,
        }
    )


# ==================== ENGAGEMENT TRACKING ====================


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def update_engagement_scores(request, campaign_id):
    """Background task to update engagement scores for all posts in a campaign"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)

    # Get all approved posts
    posts = PostScore.objects.filter(campaign=campaign, moderation_status='approved')

    updated_count = 0
    errors = []
    for post in posts:
        try:
            post.update_engagement_score()
            updated_count += 1
        except Exception as e:
            errors.append(f'post {post.id}: {str(e)}')

    # Update all user stats
    stats = UserCampaignStats.objects.filter(campaign=campaign)
    stats_updated = 0
    for stat in stats:
        try:
            stat.update_stats()
            stats_updated += 1
        except Exception as e:
            errors.append(f'stat {stat.id}: {str(e)}')

    return Response(
        {
            'message': 'Engagement scores updated',
            'posts_updated': updated_count,
            'users_updated': stats_updated,
            'errors': errors,
        }
    )


# ==================== CONSISTENCY SCORING ====================


def calculate_consistency_score(user, campaign):
    """Calculate consistency score based on posting frequency using configurable weights"""
    from api.models.campaign_extended import CampaignScoringConfig

    stats = UserCampaignStats.objects.filter(user=user, campaign=campaign).first()
    if not stats:
        return 0

    # Get scoring config
    config = CampaignScoringConfig.objects.filter(campaign=campaign).first()
    if not config:
        config = CampaignScoringConfig.objects.create(campaign=campaign)

    # Calculate based on streak and days participated with configurable weights
    max_points = float(config.max_consistency_points)
    streak_score = min(max_points / 2, stats.current_streak * float(config.streak_points_per_day))
    participation_score = min(
        max_points / 2, stats.days_participated * float(config.participation_points_per_day)
    )

    return min(max_points, streak_score + participation_score)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def update_consistency_scores(request, campaign_id):
    """Update consistency scores for all users in a campaign"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)

    # Get all users with posts in this campaign
    users = User.objects.filter(
        campaign_scores__campaign=campaign, campaign_scores__moderation_status='approved'
    ).distinct()

    updated_count = 0
    for user in users:
        consistency_score = calculate_consistency_score(user, campaign)

        # Update all approved posts for this user
        PostScore.objects.filter(user=user, campaign=campaign, moderation_status='approved').update(
            consistency_score=consistency_score
        )

        # Recalculate total scores
        posts = PostScore.objects.filter(user=user, campaign=campaign, moderation_status='approved')
        for post in posts:
            post.calculate_total_score()

        updated_count += 1

    return Response(
        {
            'message': 'Consistency scores updated',
            'users_updated': updated_count,
        }
    )


# ==================== CAMPAIGN NOTIFICATIONS ====================


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_campaign_notifications(request):
    """Get campaign-related notifications for the user"""
    from api.models.campaign import CampaignNotification

    notifications = (
        CampaignNotification.objects.filter(user=request.user)
        .select_related('campaign')
        .order_by('-created_at')[:50]
    )

    data = [
        {
            'id': notif.id,
            'campaign': {
                'id': notif.campaign.id,
                'title': notif.campaign.title,
            },
            'notification_type': notif.notification_type,
            'message': notif.message,
            'is_read': notif.is_read,
            'created_at': notif.created_at,
        }
        for notif in notifications
    ]

    return Response(data)


# ==================== GLOBAL LEADERBOARD ====================


def _compute_user_score(reel_ids, likes_w=1.0, comments_w=2.0, gifts_w=5.0):
    """Compute engagement score for a set of reel ids."""
    from api.models.gift import GiftTransaction

    likes = Vote.objects.filter(reel_id__in=reel_ids).count()
    comments = Comment.objects.filter(reel_id__in=reel_ids).count()
    gifts = GiftTransaction.objects.filter(reel_id__in=reel_ids).count()
    return likes * likes_w + comments * comments_w + gifts * gifts_w, likes, comments, gifts


def _get_profile_image(user, request):
    from api.views.campaign import get_image_url

    try:
        if hasattr(user, 'profile'):
            if user.profile.profile_photo:
                return get_image_url(user.profile.profile_photo, request)
            if user.profile.avatar:
                return get_image_url(user.profile.avatar, request)
    except Exception:  # noqa: S110 - profile image failures use the fallback URL
        pass
    return None


def _aggregate_leaderboard(*, request, campaigns, period_start, now, master_campaign, limit):
    """Shared aggregation for the weekly/monthly/grand branches of
    global_leaderboard -- they differ only in which campaigns and period
    bounds feed in, and how many leaders are returned."""
    from api.models.campaign_extended import PostScore

    campaign_ids = list(campaigns.values_list('id', flat=True))
    posts_qs = PostScore.objects.filter(
        campaign_id__in=campaign_ids,
        created_at__gte=period_start,
        created_at__lte=now,
    ).exclude(moderation_status='rejected')

    user_ids = list(posts_qs.values_list('user_id', flat=True).distinct())
    entries = []

    for user in User.objects.filter(id__in=user_ids):
        user_posts_qs = posts_qs.filter(user=user)
        reel_ids = list(user_posts_qs.values_list('reel_id', flat=True))
        score, likes, comments, gifts = _compute_user_score(reel_ids)
        user_campaign_ids = set(user_posts_qs.values_list('campaign_id', flat=True).distinct())
        entries.append(
            {
                'user_id': user.id,
                'username': user.username,
                'profile_image': _get_profile_image(user, request),
                'total_score': round(score, 1),
                'likes_count': likes,
                'comments_count': comments,
                'gifts_count': gifts,
                'post_count': len(reel_ids),
                'campaigns_count': len(user_campaign_ids),
            }
        )

    entries.sort(key=lambda x: x['total_score'], reverse=True)
    for i, e in enumerate(entries):
        e['rank'] = i + 1

    return entries[:limit]


@api_view(['GET'])
@permission_classes([AllowAny])
def global_leaderboard(request):
    """
    Global leaderboard with master campaign hierarchy support.
    ?period=daily   - top leaders per sub-campaign for a given date (?date=YYYY-MM-DD)
    ?period=weekly  - aggregated top leaders from the week's daily sub-campaigns
    ?period=monthly - aggregated top leaders from the month's weekly campaigns
    ?period=grand   - aggregated top leaders from the last 6 months of weekly campaigns
    ?master_campaign_id=<id> - filter by master campaign
    """
    from api.models.campaign_extended import PostScore
    from api.models.master_campaign import MasterCampaign

    period = request.GET.get('period', 'daily')
    master_campaign_id = request.GET.get('master_campaign_id')
    now = timezone.now()

    master_campaign = None
    if master_campaign_id:
        try:
            master_campaign = MasterCampaign.objects.get(id=master_campaign_id)
        except MasterCampaign.DoesNotExist:
            return Response({'error': 'Master campaign not found'}, status=404)

    if period == 'daily':
        date_str = request.GET.get('date', now.strftime('%Y-%m-%d'))
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = now.date()

        target_start = datetime.combine(target_date, datetime.min.time(), tzinfo=now.tzinfo)
        target_end = target_start + timedelta(days=1)

        if master_campaign:
            campaigns = (
                Campaign.objects.filter(
                    master_campaign=master_campaign,
                    campaign_type='daily',
                )
                .exclude(status='cancelled')
                .order_by('start_date')
            )
        else:
            campaigns = (
                Campaign.objects.filter(campaign_type='daily')
                .exclude(status='cancelled')
                .order_by('-created_at')
            )

        result = []
        for campaign in campaigns:
            posts_qs = PostScore.objects.filter(
                campaign=campaign,
                created_at__gte=target_start,
                created_at__lt=target_end,
            ).exclude(moderation_status='rejected')

            user_ids = list(posts_qs.values_list('user_id', flat=True).distinct())
            if not user_ids:
                continue

            entries = []
            for user in User.objects.filter(id__in=user_ids):
                reel_ids = list(posts_qs.filter(user=user).values_list('reel_id', flat=True))
                score, likes, comments, gifts = _compute_user_score(reel_ids)
                entries.append(
                    {
                        'user_id': user.id,
                        'username': user.username,
                        'profile_image': _get_profile_image(user, request),
                        'total_score': round(score, 1),
                        'likes_count': likes,
                        'comments_count': comments,
                        'gifts_count': gifts,
                        'post_count': len(reel_ids),
                    }
                )

            entries.sort(key=lambda x: x['total_score'], reverse=True)
            for i, e in enumerate(entries):
                e['rank'] = i + 1

            result.append(
                {
                    'campaign_id': campaign.id,
                    'campaign_title': campaign.title,
                    'campaign_status': campaign.status,
                    'campaign_date': campaign.start_date.strftime('%Y-%m-%d')
                    if campaign.start_date
                    else None,
                    'leaders': entries[:10],
                }
            )

        return Response(
            {
                'period': 'daily',
                'date': str(target_date),
                'master_campaign_id': master_campaign_id,
                'master_campaign_title': master_campaign.title if master_campaign else None,
                'campaigns': result,
            }
        )

    if period == 'weekly':
        period_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        campaigns = (
            Campaign.objects.filter(
                master_campaign=master_campaign,
                campaign_type='daily',
                start_date__gte=period_start,
                start_date__lte=now,
            ).exclude(status='cancelled')
            if master_campaign
            else Campaign.objects.filter(
                start_date__gte=period_start,
                start_date__lte=now,
            ).exclude(status='cancelled')
        )

        leaders = _aggregate_leaderboard(
            request=request,
            campaigns=campaigns,
            period_start=period_start,
            now=now,
            master_campaign=master_campaign,
            limit=50,
        )
        return Response(
            {
                'period': 'weekly',
                'week_start': period_start.strftime('%Y-%m-%d'),
                'master_campaign_id': master_campaign_id,
                'master_campaign_title': master_campaign.title if master_campaign else None,
                'leaders': leaders,
            }
        )

    if period == 'monthly':
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        campaigns = (
            Campaign.objects.filter(
                master_campaign=master_campaign,
                campaign_type='weekly',
                start_date__gte=period_start,
                start_date__lte=now,
            ).exclude(status='cancelled')
            if master_campaign
            else Campaign.objects.filter(
                start_date__gte=period_start,
                start_date__lte=now,
            ).exclude(status='cancelled')
        )

        leaders = _aggregate_leaderboard(
            request=request,
            campaigns=campaigns,
            period_start=period_start,
            now=now,
            master_campaign=master_campaign,
            limit=50,
        )
        return Response(
            {
                'period': 'monthly',
                'month_start': period_start.strftime('%Y-%m-%d'),
                'master_campaign_id': master_campaign_id,
                'master_campaign_title': master_campaign.title if master_campaign else None,
                'leaders': leaders,
            }
        )

    if period == 'grand':
        period_start = now - timedelta(days=180)
        campaigns = (
            Campaign.objects.filter(
                master_campaign=master_campaign,
                campaign_type='weekly',
                start_date__gte=period_start,
                start_date__lte=now,
            ).exclude(status='cancelled')
            if master_campaign
            else Campaign.objects.filter(
                start_date__gte=period_start,
                start_date__lte=now,
            ).exclude(status='cancelled')
        )

        leaders = _aggregate_leaderboard(
            request=request,
            campaigns=campaigns,
            period_start=period_start,
            now=now,
            master_campaign=master_campaign,
            limit=100,
        )
        return Response(
            {
                'period': 'grand',
                'period_start': period_start.strftime('%Y-%m-%d'),
                'master_campaign_id': master_campaign_id,
                'master_campaign_title': master_campaign.title if master_campaign else None,
                'leaders': leaders,
            }
        )

    return Response({'error': 'Invalid period'}, status=400)
