"""
API Views for Campaign Scoring Engine
Flexible scoring system endpoints for Daily, Weekly, Monthly, and Grand campaigns
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q
from datetime import datetime, timedelta

from api.models import User
from api.models.campaign import Campaign
from api.models.campaign_extended import (
    CampaignScoringConfig, UserCampaignStats, PostScore,
    Leaderboard, LeaderboardEntry, WinnerSelection, SelectedWinner,
    GamificationActivity, JudgeScore, PublicVote, GrandFinalist
)
from api.services.scoring.engine import CampaignScoringEngine
from common.security import encrypted_endpoint


# ============================================================================
# SCORING CONFIGURATION API
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_scoring_config(request, campaign_id):
    """Get scoring configuration for a campaign"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    config, created = CampaignScoringConfig.objects.get_or_create(campaign=campaign)
    
    # Build response with all configuration fields organized by type
    data = {
        'campaign_id': campaign.id,
        'campaign_type': campaign.campaign_type,
        'created': created,
        
        # Daily Campaign Settings
        'daily': {
            'top_scorer_percentage': config.daily_top_scorer_percentage,
            'random_percentage': config.daily_random_percentage,
            'engagement': {
                'likes_weight': float(config.daily_likes_weight),
                'comments_weight': float(config.daily_comments_weight),
                'shares_weight': float(config.daily_shares_weight),
                'gifts_weight': float(config.daily_gifts_weight),
            },
            'gamification': {
                'spin_reward': float(config.daily_spin_reward_weight),
                'coin_gift': float(config.daily_coin_gift_weight),
                'login_bonus': float(config.daily_login_bonus_weight),
            },
            'consistency': {
                'daily_post_points': float(config.daily_post_points),
            },
            'win_cooldown_days': config.daily_win_cooldown_days,
        },
        
        # Weekly Campaign Settings
        'weekly': {
            'engagement': {
                'likes_weight': float(config.weekly_likes_weight),
                'comments_weight': float(config.weekly_comments_weight),
                'shares_weight': float(config.weekly_shares_weight),
                'gifts_weight': float(config.weekly_gifts_weight),
            },
            'gamification': {
                'spin_reward': float(config.weekly_spin_reward_weight),
                'coin_gift': float(config.weekly_coin_gift_weight),
                'consistency_boost': float(config.weekly_consistency_boost),
            },
            'streak_bonuses': {
                '3_day': float(config.weekly_streak_3day_bonus),
                '5_day': float(config.weekly_streak_5day_bonus),
                '7_day': float(config.weekly_streak_7day_bonus),
            },
            'decay': {
                'per_missed_day': float(config.weekly_decay_per_missed_day),
                'max_days': config.weekly_decay_max_days,
            },
        },
        
        # Monthly Campaign Settings
        'monthly': {
            'engagement': {
                'likes_weight': float(config.monthly_likes_weight),
                'comments_weight': float(config.monthly_comments_weight),
                'shares_weight': float(config.monthly_shares_weight),
                'gifts_weight': float(config.monthly_gifts_weight),
            },
            'gamification': {
                'spin_reward': float(config.monthly_spin_reward_weight),
                'coin_gift': float(config.monthly_coin_gift_weight),
                'consistency_multiplier': float(config.monthly_consistency_multiplier),
            },
            'weekly_winner_bonus': float(config.monthly_weekly_winner_bonus),
            'streak_multipliers': {
                '7_day': float(config.monthly_streak_7day_multiplier),
                '14_day': float(config.monthly_streak_14day_multiplier),
                '21_day': float(config.monthly_streak_21day_multiplier),
            },
            'high_engagement': {
                'threshold': config.monthly_high_engagement_threshold,
                'bonus': float(config.monthly_high_engagement_bonus),
            },
        },
        
        # Grand Campaign Settings
        'grand': {
            'phase1_qualification': {
                'likes_weight': float(config.grand_qualification_likes_weight),
                'comments_weight': float(config.grand_qualification_comments_weight),
                'shares_weight': float(config.grand_qualification_shares_weight),
                'gifts_weight': float(config.grand_qualification_gifts_weight),
                'qualification_percentage': config.grand_qualification_percentage,
            },
            'phase2_judging': {
                'judging_weight': float(config.grand_judging_weight),
                'voting_weight': float(config.grand_voting_weight),
                'judge_criteria': {
                    'creativity_max': float(config.grand_judge_creativity_max),
                    'quality_max': float(config.grand_judge_quality_max),
                    'theme_max': float(config.grand_judge_theme_max),
                    'impact_max': float(config.grand_judge_impact_max),
                },
                'voting': {
                    'max_votes_per_user': config.grand_max_votes_per_user,
                    'vote_value': float(config.grand_vote_value),
                },
            },
        },
        
        # Legacy fields
        'legacy': {
            'max_creativity_points': float(config.max_creativity_points),
            'max_engagement_points': float(config.max_engagement_points),
            'max_consistency_points': float(config.max_consistency_points),
            'max_quality_points': float(config.max_quality_points),
            'max_theme_relevance_points': float(config.max_theme_relevance_points),
            'likes_weight': float(config.likes_weight),
            'comments_weight': float(config.comments_weight),
            'shares_weight': float(config.shares_weight),
            'streak_points_per_day': float(config.streak_points_per_day),
            'participation_points_per_day': float(config.participation_points_per_day),
        }
    }
    
    return Response(data)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAdminUser])
def admin_update_scoring_config(request, campaign_id):
    """Update scoring configuration for a campaign"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    config, _ = CampaignScoringConfig.objects.get_or_create(campaign=campaign)
    data = request.data
    
    # Update Daily settings
    if 'daily' in data:
        daily = data['daily']
        config.daily_top_scorer_percentage = daily.get('top_scorer_percentage', config.daily_top_scorer_percentage)
        config.daily_random_percentage = daily.get('random_percentage', config.daily_random_percentage)
        config.daily_win_cooldown_days = daily.get('win_cooldown_days', config.daily_win_cooldown_days)
        
        if 'engagement' in daily:
            config.daily_likes_weight = daily['engagement'].get('likes_weight', config.daily_likes_weight)
            config.daily_comments_weight = daily['engagement'].get('comments_weight', config.daily_comments_weight)
            config.daily_shares_weight = daily['engagement'].get('shares_weight', config.daily_shares_weight)
            config.daily_gifts_weight = daily['engagement'].get('gifts_weight', config.daily_gifts_weight)
        
        if 'gamification' in daily:
            config.daily_spin_reward_weight = daily['gamification'].get('spin_reward', config.daily_spin_reward_weight)
            config.daily_coin_gift_weight = daily['gamification'].get('coin_gift', config.daily_coin_gift_weight)
            config.daily_login_bonus_weight = daily['gamification'].get('login_bonus', config.daily_login_bonus_weight)
        
        if 'consistency' in daily:
            config.daily_post_points = daily['consistency'].get('daily_post_points', config.daily_post_points)
    
    # Update Weekly settings
    if 'weekly' in data:
        weekly = data['weekly']
        
        if 'engagement' in weekly:
            config.weekly_likes_weight = weekly['engagement'].get('likes_weight', config.weekly_likes_weight)
            config.weekly_comments_weight = weekly['engagement'].get('comments_weight', config.weekly_comments_weight)
            config.weekly_shares_weight = weekly['engagement'].get('shares_weight', config.weekly_shares_weight)
            config.weekly_gifts_weight = weekly['engagement'].get('gifts_weight', config.weekly_gifts_weight)
        
        if 'gamification' in weekly:
            config.weekly_spin_reward_weight = weekly['gamification'].get('spin_reward', config.weekly_spin_reward_weight)
            config.weekly_coin_gift_weight = weekly['gamification'].get('coin_gift', config.weekly_coin_gift_weight)
            config.weekly_consistency_boost = weekly['gamification'].get('consistency_boost', config.weekly_consistency_boost)
        
        if 'streak_bonuses' in weekly:
            config.weekly_streak_3day_bonus = weekly['streak_bonuses'].get('3_day', config.weekly_streak_3day_bonus)
            config.weekly_streak_5day_bonus = weekly['streak_bonuses'].get('5_day', config.weekly_streak_5day_bonus)
            config.weekly_streak_7day_bonus = weekly['streak_bonuses'].get('7_day', config.weekly_streak_7day_bonus)
        
        if 'decay' in weekly:
            config.weekly_decay_per_missed_day = weekly['decay'].get('per_missed_day', config.weekly_decay_per_missed_day)
            config.weekly_decay_max_days = weekly['decay'].get('max_days', config.weekly_decay_max_days)
    
    # Update Monthly settings
    if 'monthly' in data:
        monthly = data['monthly']
        
        if 'engagement' in monthly:
            config.monthly_likes_weight = monthly['engagement'].get('likes_weight', config.monthly_likes_weight)
            config.monthly_comments_weight = monthly['engagement'].get('comments_weight', config.monthly_comments_weight)
            config.monthly_shares_weight = monthly['engagement'].get('shares_weight', config.monthly_shares_weight)
            config.monthly_gifts_weight = monthly['engagement'].get('gifts_weight', config.monthly_gifts_weight)
        
        if 'gamification' in monthly:
            config.monthly_spin_reward_weight = monthly['gamification'].get('spin_reward', config.monthly_spin_reward_weight)
            config.monthly_coin_gift_weight = monthly['gamification'].get('coin_gift', config.monthly_coin_gift_weight)
            config.monthly_consistency_multiplier = monthly['gamification'].get('consistency_multiplier', config.monthly_consistency_multiplier)
        
        config.monthly_weekly_winner_bonus = monthly.get('weekly_winner_bonus', config.monthly_weekly_winner_bonus)
        
        if 'streak_multipliers' in monthly:
            config.monthly_streak_7day_multiplier = monthly['streak_multipliers'].get('7_day', config.monthly_streak_7day_multiplier)
            config.monthly_streak_14day_multiplier = monthly['streak_multipliers'].get('14_day', config.monthly_streak_14day_multiplier)
            config.monthly_streak_21day_multiplier = monthly['streak_multipliers'].get('21_day', config.monthly_streak_21day_multiplier)
        
        if 'high_engagement' in monthly:
            config.monthly_high_engagement_threshold = monthly['high_engagement'].get('threshold', config.monthly_high_engagement_threshold)
            config.monthly_high_engagement_bonus = monthly['high_engagement'].get('bonus', config.monthly_high_engagement_bonus)
    
    # Update Grand settings
    if 'grand' in data:
        grand = data['grand']
        
        if 'phase1_qualification' in grand:
            p1 = grand['phase1_qualification']
            config.grand_qualification_likes_weight = p1.get('likes_weight', config.grand_qualification_likes_weight)
            config.grand_qualification_comments_weight = p1.get('comments_weight', config.grand_qualification_comments_weight)
            config.grand_qualification_shares_weight = p1.get('shares_weight', config.grand_qualification_shares_weight)
            config.grand_qualification_gifts_weight = p1.get('gifts_weight', config.grand_qualification_gifts_weight)
            config.grand_qualification_percentage = p1.get('qualification_percentage', config.grand_qualification_percentage)
        
        if 'phase2_judging' in grand:
            p2 = grand['phase2_judging']
            config.grand_judging_weight = p2.get('judging_weight', config.grand_judging_weight)
            config.grand_voting_weight = p2.get('voting_weight', config.grand_voting_weight)
            
            if 'judge_criteria' in p2:
                config.grand_judge_creativity_max = p2['judge_criteria'].get('creativity_max', config.grand_judge_creativity_max)
                config.grand_judge_quality_max = p2['judge_criteria'].get('quality_max', config.grand_judge_quality_max)
                config.grand_judge_theme_max = p2['judge_criteria'].get('theme_max', config.grand_judge_theme_max)
                config.grand_judge_impact_max = p2['judge_criteria'].get('impact_max', config.grand_judge_impact_max)
            
            if 'voting' in p2:
                config.grand_max_votes_per_user = p2['voting'].get('max_votes_per_user', config.grand_max_votes_per_user)
                config.grand_vote_value = p2['voting'].get('vote_value', config.grand_vote_value)
    
    config.save()
    
    return Response({
        'message': 'Scoring configuration updated successfully',
        'campaign_type': campaign.campaign_type
    })


# ============================================================================
# SCORE CALCULATION API
# ============================================================================

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_calculate_scores(request, campaign_id):
    """
    Calculate scores for all users in a campaign using the appropriate scoring engine.
    Returns the calculated scores without saving them (preview mode).
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Initialize scoring engine
    engine = CampaignScoringEngine(campaign)
    
    # Get parameters
    date_str = request.data.get('date')
    week_start_str = request.data.get('week_start')
    month_str = request.data.get('month')
    phase = request.data.get('phase', 'qualification')
    
    # Parse dates
    calc_date = None
    week_start = None
    month_date = None
    
    if date_str:
        calc_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    if week_start_str:
        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
    if month_str:
        month_date = datetime.strptime(month_str, '%Y-%m').date()
    
    # Get all participants
    participants = UserCampaignStats.objects.filter(campaign=campaign).select_related('user')
    
    results = []
    for participant in participants:
        try:
            score_data = engine.calculate_user_score(
                participant.user,
                date=calc_date,
                week_start=week_start,
                month_date=month_date,
                phase=phase
            )
            results.append({
                'user_id': participant.user.id,
                'username': participant.user.username,
                'score': score_data
            })
        except Exception as e:
            results.append({
                'user_id': participant.user.id,
                'username': participant.user.username,
                'error': str(e)
            })
    
    # Sort by total score
    results.sort(key=lambda x: x.get('score', {}).get('total_score', 0), reverse=True)
    
    return Response({
        'campaign_type': campaign.campaign_type,
        'calculation_date': timezone.now().isoformat(),
        'parameters': {
            'date': date_str,
            'week_start': week_start_str,
            'month': month_str,
            'phase': phase,
        },
        'participant_count': len(results),
        'scores': results[:50]  # Return top 50
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_save_scores(request, campaign_id):
    """
    Calculate and save scores to the database.
    Updates UserCampaignStats with calculated scores.
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    engine = CampaignScoringEngine(campaign)
    
    # Get calculation parameters
    date_str = request.data.get('date')
    calc_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.now().date()
    
    participants = UserCampaignStats.objects.filter(campaign=campaign).select_related('user')
    
    updated_count = 0
    for participant in participants:
        try:
            score_data = engine.calculate_user_score(participant.user, date=calc_date)
            participant.total_score = score_data['total_score']
            participant.save()
            updated_count += 1
        except Exception as e:
            print(f"Error calculating score for {participant.user.username}: {e}")
    
    return Response({
        'message': f'Scores updated for {updated_count} participants',
        'updated_count': updated_count
    })


# ============================================================================
# JUDGE SCORING API (Grand Campaign Phase 2)
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_get_finalists(request, campaign_id):
    """Get all finalists for a Grand Campaign"""
    try:
        campaign = Campaign.objects.get(id=campaign_id, campaign_type='grand')
    except Campaign.DoesNotExist:
        return Response({'error': 'Grand campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    finalists = GrandFinalist.objects.filter(campaign=campaign).select_related('user')
    
    data = [{
        'finalist_id': f.id,
        'user_id': f.user.id,
        'username': f.user.username,
        'qualification_score': float(f.qualification_score),
        'qualification_rank': f.qualification_rank,
        'judge_score_total': float(f.judge_score_total),
        'vote_count': f.vote_count,
        'vote_score': float(f.vote_score),
        'final_score': float(f.final_score),
        'final_rank': f.final_rank,
        'is_winner': f.is_winner,
    } for f in finalists]
    
    return Response({
        'campaign_id': campaign.id,
        'finalists_count': len(data),
        'finalists': data
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_qualify_finalists(request, campaign_id):
    """
    Select finalists for Grand Campaign Phase 2 based on qualification scores.
    Top X% of users qualify for finals.
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id, campaign_type='grand')
    except Campaign.DoesNotExist:
        return Response({'error': 'Grand campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    engine = CampaignScoringEngine(campaign)
    
    # Get all participants with scores
    participants = UserCampaignStats.objects.filter(campaign=campaign).select_related('user')
    
    # Create entries for finalist selection
    entries = [
        type('Entry', (), {'user': p.user, 'score': float(p.total_score)})()
        for p in participants if p.total_score > 0
    ]
    
    # Select finalists
    finalists = engine.select_winners(entries, phase='qualification')
    
    # Clear existing finalists
    GrandFinalist.objects.filter(campaign=campaign).delete()
    
    # Create finalist records
    created_finalists = []
    for f in finalists:
        finalist = GrandFinalist.objects.create(
            campaign=campaign,
            user=f['user'],
            qualification_score=f['qualification_score'],
            qualification_rank=f['rank'],
            is_finalist=True
        )
        created_finalists.append({
            'user_id': finalist.user.id,
            'username': finalist.user.username,
            'rank': finalist.qualification_rank,
            'score': float(finalist.qualification_score)
        })
    
    return Response({
        'message': f'{len(created_finalists)} finalists qualified',
        'finalists': created_finalists
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_submit_judge_score(request, campaign_id):
    """
    Submit judge scores for a finalist.
    Creates or updates the judge's scores for the user.
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id, campaign_type='grand')
    except Campaign.DoesNotExist:
        return Response({'error': 'Grand campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    finalist_user_id = request.data.get('finalist_user_id')
    scores = request.data.get('scores', {})  # creativity, quality, theme, impact
    comments = request.data.get('comments', '')
    
    try:
        finalist_user = User.objects.get(id=finalist_user_id)
    except User.DoesNotExist:
        return Response({'error': 'Finalist user not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Verify user is a finalist
    if not GrandFinalist.objects.filter(campaign=campaign, user=finalist_user).exists():
        return Response({'error': 'User is not a finalist for this campaign'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Create or update judge score
    judge_score, created = JudgeScore.objects.update_or_create(
        campaign=campaign,
        user=finalist_user,
        judge=request.user,
        defaults={
            'creativity_score': scores.get('creativity', 0),
            'quality_score': scores.get('quality', 0),
            'theme_score': scores.get('theme', 0),
            'impact_score': scores.get('impact', 0),
            'judge_comments': comments
        }
    )
    
    # Update finalist aggregate judge score
    aggregate = JudgeScore.objects.filter(campaign=campaign, user=finalist_user).aggregate(
        total_creativity=Avg('creativity_score'),
        total_quality=Avg('quality_score'),
        total_theme=Avg('theme_score'),
        total_impact=Avg('impact_score')
    )
    
    total_judge_score = sum([
        aggregate['total_creativity'] or 0,
        aggregate['total_quality'] or 0,
        aggregate['total_theme'] or 0,
        aggregate['total_impact'] or 0
    ])
    
    finalist = GrandFinalist.objects.get(campaign=campaign, user=finalist_user)
    finalist.judge_score_total = total_judge_score
    finalist.save()
    
    return Response({
        'message': 'Judge score submitted successfully',
        'finalist_id': finalist_user.id,
        'judge_total_score': float(total_judge_score),
        'created': created
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_calculate_final_scores(request, campaign_id):
    """
    Calculate final scores for all finalists using Phase 2 formula:
    Final Score = (Judge Score * judging_weight) + (Vote Score * voting_weight)
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id, campaign_type='grand')
    except Campaign.DoesNotExist:
        return Response({'error': 'Grand campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    engine = CampaignScoringEngine(campaign)
    config = engine.type_config['phase2_judging']
    
    finalists = GrandFinalist.objects.filter(campaign=campaign, is_finalist=True)
    
    results = []
    for finalist in finalists:
        # Get vote count
        vote_count = PublicVote.objects.filter(campaign=campaign, finalist=finalist.user).count()
        
        # Calculate final score
        judge_scores = {
            'creativity': float(finalist.judge_score_total) / 4,  # Approximate distribution
            'quality': float(finalist.judge_score_total) / 4,
            'theme': float(finalist.judge_score_total) / 4,
            'impact': float(finalist.judge_score_total) / 4,
        }
        
        final_data = engine.calculate_grand_final_score(finalist.user, judge_scores, vote_count)
        
        # Update finalist
        finalist.vote_count = vote_count
        finalist.vote_score = final_data['breakdown']['vote_contribution']
        finalist.final_score = final_data['total_score']
        finalist.save()
        
        results.append({
            'user_id': finalist.user.id,
            'username': finalist.user.username,
            'judge_score': final_data['breakdown']['judge_score'],
            'vote_score': final_data['breakdown']['vote_score'],
            'vote_count': vote_count,
            'final_score': float(final_data['total_score']),
            'breakdown': final_data['breakdown']
        })
    
    # Sort by final score and assign ranks
    results.sort(key=lambda x: x['final_score'], reverse=True)
    for rank, result in enumerate(results, start=1):
        finalist = GrandFinalist.objects.get(campaign=campaign, user__id=result['user_id'])
        finalist.final_rank = rank
        finalist.save()
        result['final_rank'] = rank
    
    return Response({
        'message': f'Final scores calculated for {len(results)} finalists',
        'finalists': results
    })


# ============================================================================
# PUBLIC VOTING API (Grand Campaign Phase 2)
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_finalists_for_voting(request, campaign_id):
    """Get list of finalists for public voting"""
    try:
        campaign = Campaign.objects.get(id=campaign_id, campaign_type='grand')
    except Campaign.DoesNotExist:
        return Response({'error': 'Grand campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Check if campaign is in voting phase
    if campaign.status != 'voting':
        return Response({'error': 'Campaign is not in voting phase'}, status=status.HTTP_400_BAD_REQUEST)
    
    finalists = GrandFinalist.objects.filter(campaign=campaign, is_finalist=True).select_related('user')
    
    data = [{
        'finalist_id': f.id,
        'user_id': f.user.id,
        'username': f.user.username,
        'qualification_rank': f.qualification_rank,
        'vote_count': f.vote_count,
    } for f in finalists]
    
    return Response({
        'campaign_id': campaign.id,
        'campaign_status': campaign.status,
        'finalists': data
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def cast_vote(request, campaign_id):
    """Cast a vote for a finalist"""
    try:
        campaign = Campaign.objects.get(id=campaign_id, campaign_type='grand')
    except Campaign.DoesNotExist:
        return Response({'error': 'Grand campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Check if campaign is in voting phase
    if campaign.status != 'voting':
        return Response({'error': 'Campaign is not in voting phase'}, status=status.HTTP_400_BAD_REQUEST)
    
    finalist_user_id = request.data.get('finalist_user_id')
    
    try:
        finalist_user = User.objects.get(id=finalist_user_id)
    except User.DoesNotExist:
        return Response({'error': 'Finalist not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Verify user is a finalist
    if not GrandFinalist.objects.filter(campaign=campaign, user=finalist_user).exists():
        return Response({'error': 'User is not a finalist'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Check max votes per user
    config, _ = CampaignScoringConfig.objects.get_or_create(campaign=campaign)
    max_votes = config.grand_max_votes_per_user
    
    existing_votes = PublicVote.objects.filter(campaign=campaign, voter=request.user).count()
    
    if existing_votes >= max_votes:
        return Response({
            'error': f'You have already cast your maximum of {max_votes} votes'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if already voted for this finalist
    if PublicVote.objects.filter(campaign=campaign, voter=request.user, finalist=finalist_user).exists():
        return Response({'error': 'You have already voted for this finalist'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Create vote
    vote = PublicVote.objects.create(
        campaign=campaign,
        voter=request.user,
        finalist=finalist_user,
        vote_value=config.grand_vote_value,
        ip_address=request.META.get('REMOTE_ADDR')
    )
    
    return Response({
        'message': 'Vote cast successfully',
        'vote_id': vote.id,
        'votes_remaining': max_votes - existing_votes - 1
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_user_votes(request, campaign_id):
    """Get votes cast by current user in a campaign"""
    votes = PublicVote.objects.filter(
        campaign_id=campaign_id,
        voter=request.user
    ).select_related('finalist')
    
    data = [{
        'vote_id': v.id,
        'finalist_id': v.finalist.id,
        'finalist_username': v.finalist.username,
        'vote_value': float(v.vote_value),
        'created_at': v.created_at
    } for v in votes]
    
    return Response({
        'votes_cast': len(data),
        'votes': data
    })
