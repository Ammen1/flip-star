from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Sum, Avg, Count, Q
from datetime import datetime, timedelta
import random

from .models import User, Reel
from .models_campaign import Campaign
from .models_campaign_extended import (
    CampaignTheme, PostScore, UserCampaignStats, Leaderboard, LeaderboardEntry,
    WinnerSelection, SelectedWinner, CampaignBadge
)

def get_image_url(image_field, request=None):
    """Get absolute image URL - handles both local files and Cloudinary URLs"""
    if not image_field:
        return None
    try:
        url = image_field.url
        if not url:
            return None
        if url.startswith('http'):
            return url  # Already absolute (Cloudinary, S3, etc.)
        if request:
            return request.build_absolute_uri(url)
        return f"https://postworq.onrender.com{url}"
    except:
        return None

# ==================== THEME MANAGEMENT ====================

@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def admin_campaign_themes(request, campaign_id):
    """List or create themes for a campaign"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        themes = CampaignTheme.objects.filter(campaign=campaign)
        data = [{
            'id': theme.id,
            'title': theme.title,
            'description': theme.description,
            'week_number': theme.week_number,
            'start_date': theme.start_date,
            'end_date': theme.end_date,
            'hashtags': theme.hashtags or [],
            'is_active': theme.is_active,
            'posts_count': theme.theme_posts.count(),
        } for theme in themes]
        return Response({'themes': data})
    
    elif request.method == 'POST':
        title = request.data.get('title')
        description = request.data.get('description')
        week_number = request.data.get('week_number')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        
        if not all([title, description, week_number, start_date, end_date]):
            return Response({'error': 'Missing required fields'}, status=status.HTTP_400_BAD_REQUEST)
        
        hashtags = request.data.get('hashtags', [])
        if isinstance(hashtags, str):
            hashtags = [h.strip() for h in hashtags.split(',') if h.strip()]
        
        theme = CampaignTheme.objects.create(
            campaign=campaign,
            title=title,
            description=description,
            week_number=week_number,
            start_date=start_date,
            end_date=end_date,
            hashtags=hashtags
        )
        
        return Response({
            'id': theme.id,
            'title': theme.title,
            'week_number': theme.week_number,
            'hashtags': theme.hashtags,
            'message': 'Theme created successfully'
        }, status=status.HTTP_201_CREATED)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAdminUser])
def admin_campaign_theme_detail(request, theme_id):
    """Update or delete a theme"""
    try:
        theme = CampaignTheme.objects.get(id=theme_id)
    except CampaignTheme.DoesNotExist:
        return Response({'error': 'Theme not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'PUT':
        theme.title = request.data.get('title', theme.title)
        theme.description = request.data.get('description', theme.description)
        theme.week_number = request.data.get('week_number', theme.week_number)
        theme.start_date = request.data.get('start_date', theme.start_date)
        theme.end_date = request.data.get('end_date', theme.end_date)
        if 'hashtags' in request.data:
            hashtags = request.data['hashtags']
            if isinstance(hashtags, str):
                hashtags = [h.strip() for h in hashtags.split(',') if h.strip()]
            theme.hashtags = hashtags
        theme.save()
        
        return Response({'message': 'Theme updated successfully'})
    
    elif request.method == 'DELETE':
        theme.delete()
        return Response({'message': 'Theme deleted successfully'})

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_activate_theme(request, theme_id):
    """Activate a specific theme"""
    try:
        theme = CampaignTheme.objects.get(id=theme_id)
        theme.activate()
        return Response({'message': f'Theme "{theme.title}" activated'})
    except CampaignTheme.DoesNotExist:
        return Response({'error': 'Theme not found'}, status=status.HTTP_404_NOT_FOUND)

# ==================== POST MODERATION ====================

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_campaign_posts_pending(request, campaign_id):
    """Get pending campaign posts for moderation"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    pending_scores = PostScore.objects.filter(
        campaign=campaign,
        moderation_status='pending'
    ).select_related('user', 'reel', 'theme')
    
    data = [{
        'id': score.id,
        'reel_id': score.reel.id,
        'user': {
            'id': score.user.id,
            'username': score.user.username,
        },
        'theme': {
            'id': score.theme.id,
            'title': score.theme.title,
        } if score.theme else None,
        'reel': {
            'caption': score.reel.caption,
            'hashtags': score.reel.hashtags,
            'image': score.reel.image.url if score.reel.image else None,
            'media': score.reel.media.url if score.reel.media else None,
            'created_at': score.reel.created_at,
        },
        'created_at': score.created_at,
    } for score in pending_scores]
    
    return Response(data)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_moderate_post(request, score_id):
    """Approve or reject a campaign post"""
    try:
        score = PostScore.objects.get(id=score_id)
    except PostScore.DoesNotExist:
        return Response({'error': 'Post score not found'}, status=status.HTTP_404_NOT_FOUND)
    
    action = request.data.get('action')  # 'approve' or 'reject'
    
    if action == 'approve':
        from .models_campaign_extended import CampaignScoringConfig
        
        # Get scoring config
        config = CampaignScoringConfig.objects.filter(campaign=score.campaign).first()
        if not config:
            config = CampaignScoringConfig.objects.create(campaign=score.campaign)
        
        score.moderation_status = 'approved'
        score.moderated_by = request.user
        score.moderated_at = timezone.now()
        
        # Assign initial scores (capped by config max points)
        creativity = request.data.get('creativity_score', 0)
        quality = request.data.get('quality_score', float(config.max_quality_points) * 0.7)  # Default 70% of max
        theme_relevance = request.data.get('theme_relevance_score', float(config.max_theme_relevance_points) * 0.5)  # Default 50% of max
        
        score.creativity_score = min(float(config.max_creativity_points), creativity)
        score.quality_score = min(float(config.max_quality_points), quality)
        score.theme_relevance_score = min(float(config.max_theme_relevance_points), theme_relevance)
        
        # Calculate engagement and consistency scores
        score.update_engagement_score()
        
        # Update user stats
        stats, created = UserCampaignStats.objects.get_or_create(
            user=score.user,
            campaign=score.campaign
        )
        stats.update_stats()
        
        score.save()
        
        return Response({'message': 'Post approved successfully'})
    
    elif action == 'reject':
        score.moderation_status = 'rejected'
        score.rejection_reason = request.data.get('rejection_reason', '')
        score.moderated_by = request.user
        score.moderated_at = timezone.now()
        score.save()
        
        # Update user stats
        stats, created = UserCampaignStats.objects.get_or_create(
            user=score.user,
            campaign=score.campaign
        )
        stats.update_stats()
        
        return Response({'message': 'Post rejected'})
    
    else:
        return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_update_post_scores(request, score_id):
    """Update individual score components for a post"""
    try:
        score = PostScore.objects.get(id=score_id)
    except PostScore.DoesNotExist:
        return Response({'error': 'Post score not found'}, status=status.HTTP_404_NOT_FOUND)
    
    from .models_campaign_extended import CampaignScoringConfig
    
    # Get scoring config
    config = CampaignScoringConfig.objects.filter(campaign=score.campaign).first()
    if not config:
        config = CampaignScoringConfig.objects.create(campaign=score.campaign)
    
    # Update scores with configurable max points
    if 'creativity_score' in request.data:
        score.creativity_score = min(float(config.max_creativity_points), float(request.data['creativity_score']))
    if 'quality_score' in request.data:
        score.quality_score = min(float(config.max_quality_points), float(request.data['quality_score']))
    if 'theme_relevance_score' in request.data:
        score.theme_relevance_score = min(float(config.max_theme_relevance_points), float(request.data['theme_relevance_score']))
    
    score.calculate_total_score()
    
    # Update user stats
    stats, created = UserCampaignStats.objects.get_or_create(
        user=score.user,
        campaign=score.campaign
    )
    stats.update_stats()
    
    return Response({
        'message': 'Scores updated',
        'total_score': float(score.total_score)
    })

# ==================== LEADERBOARD MANAGEMENT ====================

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_generate_leaderboard(request, campaign_id):
    """Generate leaderboard for a specific period"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    period_type = request.data.get('period_type', 'daily')  # daily, weekly, monthly, overall
    
    # Determine period dates
    now = timezone.now()
    if period_type == 'daily':
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=1)
    elif period_type == 'weekly':
        period_start = now - timedelta(days=now.weekday())
        period_start = period_start.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=7)
    elif period_type == 'monthly':
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = period_start + timedelta(days=32)
        period_end = next_month.replace(day=1)
    else:  # overall
        period_start = campaign.start_date
        period_end = campaign.entry_deadline
    
    # Mark previous leaderboards as not current
    Leaderboard.objects.filter(
        campaign=campaign,
        period_type=period_type
    ).update(is_current=False)
    
    # Create new leaderboard
    leaderboard = Leaderboard.objects.create(
        campaign=campaign,
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        is_current=True
    )
    
    # Get user stats and rank them
    stats = UserCampaignStats.objects.filter(
        campaign=campaign
    ).order_by('-total_score')
    
    # Create leaderboard entries
    for rank, stat in enumerate(stats, start=1):
        LeaderboardEntry.objects.create(
            leaderboard=leaderboard,
            user=stat.user,
            rank=rank,
            score=stat.total_score,
            posts_count=stat.approved_posts
        )
        
        # Update user's rank in stats
        if period_type == 'daily':
            stat.daily_rank = rank
        elif period_type == 'weekly':
            stat.weekly_rank = rank
        elif period_type == 'monthly':
            stat.monthly_rank = rank
        else:
            stat.overall_rank = rank
        stat.save()
    
    return Response({
        'message': f'{period_type.capitalize()} leaderboard generated',
        'leaderboard_id': leaderboard.id,
        'entries_count': stats.count()
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_leaderboard(request, campaign_id):
    """Get leaderboard for a campaign - calculates real-time scores using campaign scoring configuration"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)

    period_type = request.query_params.get('period', 'overall')

    # Initialize scoring engine to get campaign's configured weights
    from .campaign_scoring_engine import CampaignScoringEngine
    engine = CampaignScoringEngine(campaign)
    config = engine.type_config

    # Get engagement weights from config (fallback to 0 if not present)
    engagement_weights = config.get('engagement', {})
    if campaign.campaign_type == 'grand':
        # Grand uses phase1_qualification for weights
        engagement_weights = config.get('phase1_qualification', {})
    
    likes_weight = engagement_weights.get('likes_weight', 0)
    comments_weight = engagement_weights.get('comments_weight', 0)
    shares_weight = engagement_weights.get('shares_weight', 0)
    gifts_weight = engagement_weights.get('gifts_weight', 0)

    # Determine date range based on period_type
    now = timezone.now()
    if period_type == 'daily':
        start_date = now.date()
        posts_qs = PostScore.objects.filter(
            campaign=campaign,
            moderation_status='approved',
            created_at__date=start_date
        )
    elif period_type == 'weekly':
        week_start = now - timedelta(days=now.weekday())
        posts_qs = PostScore.objects.filter(
            campaign=campaign,
            moderation_status='approved',
            created_at__gte=week_start.replace(hour=0, minute=0, second=0)
        )
    elif period_type == 'monthly':
        posts_qs = PostScore.objects.filter(
            campaign=campaign,
            moderation_status='approved',
            created_at__year=now.year,
            created_at__month=now.month
        )
    else:  # overall
        posts_qs = PostScore.objects.filter(
            campaign=campaign,
            moderation_status='approved'
        )

    # Get all unique users with posts in this campaign/period
    user_ids = list(posts_qs.values_list('user_id', flat=True).distinct())
    
    # Get all users who have participated
    from django.contrib.auth import get_user_model
    User = get_user_model()
    users = User.objects.filter(id__in=user_ids)

    from .models import Vote, Comment
    from .models_gift import GiftTransaction

    entries_data = []
    for user in users:
        # Get user's posts in this campaign/period
        user_posts = posts_qs.filter(user=user).select_related('reel')
        reel_ids = list(user_posts.values_list('reel_id', flat=True))
        
        # Count engagement metrics
        total_likes = Vote.objects.filter(reel_id__in=reel_ids).count()
        total_comments = Comment.objects.filter(reel_id__in=reel_ids).count()
        total_shares = 0  # TODO: implement shares tracking
        
        # Count unique gifters per post (distinct senders)
        total_gifters = 0
        for reel_id in reel_ids:
            total_gifters += GiftTransaction.objects.filter(reel_id=reel_id).values('sender').distinct().count()
        
        # Calculate score using campaign weights: score = likes*pt + comments*pt + shares*pt + gifts*pt
        calculated_score = (
            total_likes * likes_weight +
            total_comments * comments_weight +
            total_shares * shares_weight +
            total_gifters * gifts_weight
        )
        
        # Get user profile image
        profile_image = None
        try:
            if hasattr(user, 'profile'):
                profile_image = get_image_url(user.profile.profile_photo, request)
                if not profile_image:
                    profile_image = get_image_url(user.profile.avatar, request)
        except:
            pass
        
        entries_data.append({
            'user_id': user.id,
            'username': user.username,
            'profile_image': profile_image,
            'total_score': float(calculated_score),
            'post_count': len(reel_ids),
            'likes_count': total_likes,
            'comments_count': total_comments,
            'shares_count': total_shares,
            'gifts_count': total_gifters,
            'weights': {
                'likes': likes_weight,
                'comments': comments_weight,
                'shares': shares_weight,
                'gifts': gifts_weight,
            }
        })
    
    # Sort by calculated score descending
    entries_data.sort(key=lambda x: x['total_score'], reverse=True)
    
    # Add ranks after sorting
    for idx, entry in enumerate(entries_data[:100]):
        entry['rank'] = idx + 1

    return Response({
        'period_type': period_type,
        'campaign_type': campaign.campaign_type,
        'entries': entries_data[:100]
    })

# ==================== WINNER SELECTION ====================

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_select_winners(request, campaign_id):
    """Select winners for a period"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    selection_type = request.data.get('selection_type', 'daily')
    leaderboard_id = request.data.get('leaderboard_id')
    
    try:
        leaderboard = Leaderboard.objects.get(id=leaderboard_id)
    except Leaderboard.DoesNotExist:
        return Response({'error': 'Leaderboard not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Create winner selection
    selection = WinnerSelection.objects.create(
        campaign=campaign,
        selection_type=selection_type,
        leaderboard=leaderboard
    )
    
    # Get leaderboard entries
    entries = LeaderboardEntry.objects.filter(leaderboard=leaderboard).order_by('rank')
    
    if campaign.campaign_type == 'daily':
        # Daily: configurable % top scorers, % random
        config, _ = CampaignScoringConfig.objects.get_or_create(campaign=campaign)
        total_winners = request.data.get('total_winners', campaign.winner_count)
        
        # Calculate split
        top_percentage = config.daily_top_scorer_percentage / 100.0
        top_count = int(total_winners * top_percentage)
        random_count = total_winners - top_count
        
        # Select top scorers
        top_entries = entries[:top_count]
        for idx, entry in enumerate(top_entries, start=1):
            SelectedWinner.objects.create(
                selection=selection,
                user=entry.user,
                rank=idx,
                final_score=entry.score,
                selection_method='top_scorer'
            )
        
        # Select random participants from the rest
        remaining_entries = list(entries[top_count:])
        if len(remaining_entries) > random_count:
            random_entries = random.sample(remaining_entries, random_count)
        else:
            random_entries = remaining_entries
        
        for idx, entry in enumerate(random_entries, start=top_count + 1):
            SelectedWinner.objects.create(
                selection=selection,
                user=entry.user,
                rank=idx,
                final_score=entry.score,
                selection_method='random'
            )
            
    elif campaign.campaign_type in ['weekly', 'monthly']:
        # Weekly/Monthly: Top scorers only, check if won already
        winner_count = request.data.get('winner_count', campaign.winner_count)
        
        # Filter out users who have already won in this cycle
        eligible_entries = []
        for entry in entries:
            stat = UserCampaignStats.objects.filter(user=entry.user, campaign=campaign).first()
            if not stat or not stat.has_won_current_cycle:
                eligible_entries.append(entry)
                
        top_entries = eligible_entries[:winner_count]
        
        for idx, entry in enumerate(top_entries, start=1):
            SelectedWinner.objects.create(
                selection=selection,
                user=entry.user,
                rank=idx,
                final_score=entry.score,
                selection_method='top_scorer'
            )
            
            # Mark user as having won this cycle
            stat = UserCampaignStats.objects.get(user=entry.user, campaign=campaign)
            stat.has_won_current_cycle = True
            stat.last_win_date = timezone.now()
            stat.save()
            
    elif campaign.campaign_type == 'grand':
        # Grand campaign logic (Voting + Scoring)
        winner_count = request.data.get('winner_count', campaign.winner_count)
        top_entries = entries[:winner_count]
        
        for idx, entry in enumerate(top_entries, start=1):
            SelectedWinner.objects.create(
                selection=selection,
                user=entry.user,
                rank=idx,
                final_score=entry.score,
                selection_method='top_scorer'
            )
    
    selection.is_finalized = True
    selection.finalized_at = timezone.now()
    selection.finalized_by = request.user
    selection.save()
    
    return Response({
        'message': f'{selection_type.capitalize()} winners selected',
        'selection_id': selection.id,
        'winners_count': selection.winners.count()
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_campaign_winners(request, campaign_id):
    """Get winners for a campaign"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    selection_type = request.query_params.get('type', 'overall')
    
    selections = WinnerSelection.objects.filter(
        campaign=campaign,
        selection_type=selection_type,
        is_finalized=True
    ).order_by('-finalized_at')
    
    data = []
    for selection in selections:
        winners = SelectedWinner.objects.filter(selection=selection).select_related('user')
        data.append({
            'selection_id': selection.id,
            'selection_type': selection.selection_type,
            'finalized_at': selection.finalized_at,
            'winners': [{
                'rank': winner.rank,
                'user': {
                    'id': winner.user.id,
                    'username': winner.user.username,
                },
                'final_score': float(winner.final_score),
                'selection_method': winner.selection_method,
                'prize_claimed': winner.prize_claimed,
            } for winner in winners]
        })
    
    return Response(data)

# ==================== ANALYTICS ====================

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_campaign_analytics(request, campaign_id):
    """Get comprehensive analytics for a campaign"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Overall stats
    total_participants = UserCampaignStats.objects.filter(campaign=campaign).count()
    total_posts = PostScore.objects.filter(campaign=campaign).count()
    approved_posts = PostScore.objects.filter(campaign=campaign, moderation_status='approved').count()
    pending_posts = PostScore.objects.filter(campaign=campaign, moderation_status='pending').count()
    rejected_posts = PostScore.objects.filter(campaign=campaign, moderation_status='rejected').count()
    
    # Score statistics
    score_stats = PostScore.objects.filter(
        campaign=campaign,
        moderation_status='approved'
    ).aggregate(
        avg_total=Avg('total_score'),
        avg_creativity=Avg('creativity_score'),
        avg_engagement=Avg('engagement_score'),
        avg_quality=Avg('quality_score'),
    )
    
    # Theme participation
    themes = CampaignTheme.objects.filter(campaign=campaign)
    theme_data = [{
        'week_number': theme.week_number,
        'title': theme.title,
        'posts_count': theme.theme_posts.count(),
        'is_active': theme.is_active,
    } for theme in themes]
    
    # Top performers
    top_users = UserCampaignStats.objects.filter(campaign=campaign).order_by('-total_score')[:10]
    top_performers = [{
        'username': stat.user.username,
        'total_score': float(stat.total_score),
        'posts_count': stat.approved_posts,
        'rank': stat.overall_rank,
    } for stat in top_users]
    
    return Response({
        'campaign': {
            'id': campaign.id,
            'title': campaign.title,
            'status': campaign.status,
        },
        'participation': {
            'total_participants': total_participants,
            'total_posts': total_posts,
            'approved_posts': approved_posts,
            'pending_posts': pending_posts,
            'rejected_posts': rejected_posts,
        },
        'score_statistics': {
            'average_total_score': float(score_stats['avg_total'] or 0),
            'average_creativity': float(score_stats['avg_creativity'] or 0),
            'average_engagement': float(score_stats['avg_engagement'] or 0),
            'average_quality': float(score_stats['avg_quality'] or 0),
        },
        'themes': theme_data,
        'top_performers': top_performers,
    })
