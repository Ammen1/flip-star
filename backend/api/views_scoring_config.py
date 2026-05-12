from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models_campaign import Campaign
from .models_campaign_extended import CampaignScoringConfig

@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def admin_scoring_config(request, campaign_id):
    """Get or create scoring configuration for a campaign"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        # Get or create default config
        config, created = CampaignScoringConfig.objects.get_or_create(campaign=campaign)
        
        return Response({
            'id': config.id,
            'campaign_id': campaign.id,
            'max_points': {
                'creativity': float(config.max_creativity_points),
                'engagement': float(config.max_engagement_points),
                'consistency': float(config.max_consistency_points),
                'quality': float(config.max_quality_points),
                'theme_relevance': float(config.max_theme_relevance_points),
                'total': float(config.get_total_max_points()),
            },
            'engagement_weights': {
                'likes': float(config.likes_weight),
                'comments': float(config.comments_weight),
                'shares': float(config.shares_weight),
            },
            'consistency_settings': {
                'streak_points_per_day': float(config.streak_points_per_day),
                'participation_points_per_day': float(config.participation_points_per_day),
            },
            'created_at': config.created_at,
            'updated_at': config.updated_at,
        })
    
    elif request.method == 'POST':
        # Update or create config
        config, created = CampaignScoringConfig.objects.get_or_create(campaign=campaign)
        
        # Update max points
        if 'max_creativity_points' in request.data:
            config.max_creativity_points = request.data['max_creativity_points']
        if 'max_engagement_points' in request.data:
            config.max_engagement_points = request.data['max_engagement_points']
        if 'max_consistency_points' in request.data:
            config.max_consistency_points = request.data['max_consistency_points']
        if 'max_quality_points' in request.data:
            config.max_quality_points = request.data['max_quality_points']
        if 'max_theme_relevance_points' in request.data:
            config.max_theme_relevance_points = request.data['max_theme_relevance_points']
        
        # Update engagement weights
        if 'likes_weight' in request.data:
            config.likes_weight = request.data['likes_weight']
        if 'comments_weight' in request.data:
            config.comments_weight = request.data['comments_weight']
        if 'shares_weight' in request.data:
            config.shares_weight = request.data['shares_weight']
        
        # Update consistency settings
        if 'streak_points_per_day' in request.data:
            config.streak_points_per_day = request.data['streak_points_per_day']
        if 'participation_points_per_day' in request.data:
            config.participation_points_per_day = request.data['participation_points_per_day']
        
        config.save()
        
        return Response({
            'message': 'Scoring configuration updated successfully',
            'total_max_points': float(config.get_total_max_points()),
        })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_scoring_config(request, campaign_id):
    """Get scoring configuration for a campaign (public view)"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    config, created = CampaignScoringConfig.objects.get_or_create(campaign=campaign)
    
    return Response({
        'max_points': {
            'creativity': float(config.max_creativity_points),
            'engagement': float(config.max_engagement_points),
            'consistency': float(config.max_consistency_points),
            'quality': float(config.max_quality_points),
            'theme_relevance': float(config.max_theme_relevance_points),
            'total': float(config.get_total_max_points()),
        },
        'description': {
            'creativity': 'Manual admin scoring or community voting',
            'engagement': 'Based on likes, comments, and shares',
            'consistency': 'Posting frequency and streaks',
            'quality': 'Video clarity and resolution',
            'theme_relevance': 'Match with current theme',
        }
    })

@api_view(['POST'])
@permission_classes([IsAdminUser])
def reset_scoring_config(request, campaign_id):
    """Reset scoring configuration to defaults"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Delete existing config
    CampaignScoringConfig.objects.filter(campaign=campaign).delete()
    
    # Create new default config
    config = CampaignScoringConfig.objects.create(campaign=campaign)
    
    return Response({
        'message': 'Scoring configuration reset to defaults',
        'total_max_points': float(config.get_total_max_points()),
    })
