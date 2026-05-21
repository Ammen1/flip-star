from django.shortcuts import get_object_or_404
from django.db.models import Q, Sum, F, Count
from django.utils import timezone
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from decimal import Decimal, InvalidOperation

from .models import User, Reel, UserProfile
from .models_boost import BoostConfig, BoostCampaign, BoostImpression, BoostEngagement, BoostStats
from datetime import timedelta


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_boost_config(request):
    """Get current boost configuration and pricing"""
    try:
        config = BoostConfig.objects.first()
        if not config:
            config = BoostConfig.objects.create()
        
        return Response({
            'base_hourly_rate': float(config.base_hourly_rate),
            'discounts': {
                '6hr': config.discount_6hr,
                '12hr': config.discount_12hr,
                '24hr': config.discount_24hr,
                '3day': config.discount_3day,
                '7day': config.discount_7day,
            },
            'duration_options': [
                {'hours': 1, 'label': '1 Hour', 'cost': float(config.calculate_cost(1, False))},
                {'hours': 6, 'label': '6 Hours', 'label_extra': '17% off', 'cost': float(config.calculate_cost(6, False))},
                {'hours': 12, 'label': '12 Hours', 'label_extra': '33% off', 'cost': float(config.calculate_cost(12, False))},
                {'hours': 24, 'label': '24 Hours', 'label_extra': '42% off', 'cost': float(config.calculate_cost(24, False))},
                {'hours': 72, 'label': '3 Days', 'label_extra': '56% off', 'cost': float(config.calculate_cost(72, False))},
                {'hours': 168, 'label': '7 Days', 'label_extra': '71% off', 'cost': float(config.calculate_cost(168, False))},
            ],
            'premium_targeting_surcharge': config.premium_targeting_surcharge,
            'platform_fee_percent': config.platform_fee_percent,
            'base_impression_rate': config.base_impression_rate,
            'user_limits': {
                'max_daily_boosts': config.max_daily_boosts_per_user,
                'max_active_per_post': config.max_active_boosts_per_post,
            },
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def calculate_boost_cost(request):
    """Calculate boost cost for given parameters"""
    try:
        duration_hours = int(request.data.get('duration_hours'))
        target_gender = request.data.get('target_gender')
        target_age_min = request.data.get('target_age_min')
        target_age_max = request.data.get('target_age_max')
        target_location = request.data.get('target_location')
        
        config = BoostConfig.objects.first()
        if not config:
            config = BoostConfig.objects.create()
        
        # Check if premium targeting is used
        has_premium_targeting = bool(
            target_gender and target_gender != 'all' or
            target_age_min or target_age_max or
            target_location
        )
        
        cost = config.calculate_cost(duration_hours, has_premium_targeting)
        expected_impressions = config.get_expected_impressions(cost)
        
        return Response({
            'cost': float(cost),
            'expected_impressions': expected_impressions,
            'has_premium_targeting': has_premium_targeting,
            'premium_surcharge_applied': has_premium_targeting,
        })
    except Exception as e:
        return Response({'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_boost_campaign(request):
    """Create a new boost campaign"""
    try:
        user = request.user
        reel_id = request.data.get('reel_id')
        duration_hours = int(request.data.get('duration_hours'))
        target_gender = request.data.get('target_gender', 'all')
        target_age_min = request.data.get('target_age_min')
        target_age_max = request.data.get('target_age_max')
        target_location = request.data.get('target_location', '')
        
        # Validate reel exists and belongs to user
        reel = get_object_or_404(Reel, id=reel_id, user=user)
        
        # Get or create config
        config = BoostConfig.objects.first()
        if not config:
            config = BoostConfig.objects.create()
        
        # Check user limits
        today = timezone.now().date()
        boosts_today = BoostCampaign.objects.filter(
            user=user,
            created_at__date=today
        ).count()
        
        if boosts_today >= config.max_daily_boosts_per_user:
            return Response({
                'error': f'Daily boost limit reached ({config.max_daily_boosts_per_user} per day)'
            }, status=400)
        
        # Check active boosts on this post
        active_boosts = BoostCampaign.objects.filter(
            reel=reel,
            status='active',
            end_time__gt=timezone.now()
        ).count()
        
        if active_boosts >= config.max_active_boosts_per_post:
            return Response({
                'error': f'Maximum active boosts for this post reached ({config.max_active_boosts_per_post})'
            }, status=400)
        
        # Check if premium targeting is used
        has_premium_targeting = bool(
            target_gender and target_gender != 'all' or
            target_age_min or target_age_max or
            target_location
        )
        
        # Calculate cost
        cost = config.calculate_cost(duration_hours, has_premium_targeting)
        expected_impressions = config.get_expected_impressions(cost)
        
        # Check user has enough coins
        profile = user.profile
        if profile.coins < int(cost):
            return Response({
                'error': 'Insufficient coins',
                'required': int(cost),
                'available': profile.coins
            }, status=400)
        
        # Calculate hourly budget for pacing
        hourly_budget = cost / duration_hours
        
        # Use transaction to ensure atomicity
        with transaction.atomic():
            # Deduct coins
            profile.coins -= int(cost)
            profile.coins_spent_total += int(cost)
            profile.save()
            
            # Create campaign
            campaign = BoostCampaign.objects.create(
                user=user,
                reel=reel,
                duration_hours=duration_hours,
                coins_spent=cost,
                coins_remaining=cost,
                end_time=timezone.now() + timedelta(hours=duration_hours),
                expected_impressions=expected_impressions,
                hourly_budget=hourly_budget,
                target_gender=target_gender if target_gender != 'all' else None,
                target_age_min=int(target_age_min) if target_age_min else None,
                target_age_max=int(target_age_max) if target_age_max else None,
                target_location=target_location if target_location else None,
            )
            
            # Update reel
            reel.is_boosted = True
            reel.active_boost_campaign = campaign
            reel.save()
        
        return Response({
            'success': True,
            'campaign_id': campaign.id,
            'cost': float(cost),
            'expected_impressions': expected_impressions,
            'end_time': campaign.end_time.isoformat(),
            'remaining_coins': profile.coins,
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_boost_campaigns(request):
    """Get all boost campaigns for the current user"""
    try:
        user = request.user
        campaigns = BoostCampaign.objects.filter(user=user).order_by('-created_at')
        
        campaigns_data = []
        for campaign in campaigns:
            campaigns_data.append({
                'id': campaign.id,
                'reel_id': campaign.reel.id,
                'reel_caption': campaign.reel.caption[:100] if campaign.reel.caption else '',
                'duration_hours': campaign.duration_hours,
                'coins_spent': float(campaign.coins_spent),
                'coins_remaining': float(campaign.coins_remaining),
                'start_time': campaign.start_time.isoformat(),
                'end_time': campaign.end_time.isoformat(),
                'status': campaign.status,
                'expected_impressions': campaign.expected_impressions,
                'impressions_served': campaign.impressions_served,
                'engagement_count': campaign.engagement_count,
                'progress_percent': campaign.get_progress_percent(),
                'time_remaining_hours': campaign.get_time_remaining(),
                'is_active': campaign.is_active(),
                'targeting': {
                    'gender': campaign.target_gender,
                    'age_min': campaign.target_age_min,
                    'age_max': campaign.target_age_max,
                    'location': campaign.target_location,
                } if campaign.target_gender or campaign.target_age_min or campaign.target_location else None,
            })
        
        return Response({'campaigns': campaigns_data})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_boost_campaign_detail(request, campaign_id):
    """Get detailed information about a specific boost campaign"""
    try:
        user = request.user
        campaign = get_object_or_404(BoostCampaign, id=campaign_id, user=user)
        
        # Get engagement breakdown
        engagements = campaign.engagements.values('engagement_type').annotate(
            count=Count('id')
        ).order_by('engagement_type')
        
        engagement_breakdown = {e['engagement_type']: e['count'] for e in engagements}
        
        # Get daily stats
        daily_stats = campaign.daily_stats.order_by('-date')[:7]
        
        return Response({
            'id': campaign.id,
            'reel_id': campaign.reel.id,
            'reel_caption': campaign.reel.caption[:100] if campaign.reel.caption else '',
            'duration_hours': campaign.duration_hours,
            'coins_spent': float(campaign.coins_spent),
            'coins_remaining': float(campaign.coins_remaining),
            'start_time': campaign.start_time.isoformat(),
            'end_time': campaign.end_time.isoformat(),
            'status': campaign.status,
            'expected_impressions': campaign.expected_impressions,
            'impressions_served': campaign.impressions_served,
            'engagement_count': campaign.engagement_count,
            'progress_percent': campaign.get_progress_percent(),
            'time_remaining_hours': campaign.get_time_remaining(),
            'is_active': campaign.is_active(),
            'engagement_breakdown': engagement_breakdown,
            'daily_stats': [
                {
                    'date': stat.date.isoformat(),
                    'impressions': stat.impressions_served,
                    'engagements': stat.engagements,
                    'coins_spent': float(stat.coins_spent),
                }
                for stat in daily_stats
            ],
            'targeting': {
                'gender': campaign.target_gender,
                'age_min': campaign.target_age_min,
                'age_max': campaign.target_age_max,
                'location': campaign.target_location,
            } if campaign.target_gender or campaign.target_age_min or campaign.target_location else None,
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_boost_campaign(request, campaign_id):
    """Cancel an active boost campaign with refund"""
    try:
        user = request.user
        campaign = get_object_or_404(BoostCampaign, id=campaign_id, user=user)
        
        if campaign.status != 'active':
            return Response({'error': 'Campaign is not active'}, status=400)
        
        config = BoostConfig.objects.first()
        if not config:
            config = BoostConfig.objects.create()
        
        # Calculate refund
        refund_amount = campaign.coins_remaining
        cancellation_fee = refund_amount * (Decimal(config.cancellation_fee_percent) / Decimal('100'))
        final_refund = refund_amount - cancellation_fee
        
        # Use transaction
        with transaction.atomic():
            # Refund coins
            user.profile.coins += int(final_refund)
            user.profile.save()
            
            # Update campaign
            campaign.status = 'cancelled'
            campaign.cancelled_at = timezone.now()
            campaign.coins_remaining = Decimal('0')
            campaign.refund_amount = final_refund
            campaign.refunded_at = timezone.now()
            campaign.save()
            
            # Update reel if this was the active campaign
            if campaign.reel.active_boost_campaign == campaign:
                campaign.reel.is_boosted = False
                campaign.reel.active_boost_campaign = None
                campaign.reel.save()
        
        return Response({
            'success': True,
            'refund_amount': float(final_refund),
            'cancellation_fee': float(cancellation_fee),
            'remaining_coins': user.profile.coins,
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def pause_boost_campaign(request, campaign_id):
    """Pause an active boost campaign"""
    try:
        user = request.user
        campaign = get_object_or_404(BoostCampaign, id=campaign_id, user=user)
        
        if campaign.status != 'active':
            return Response({'error': 'Campaign is not active'}, status=400)
        
        campaign.status = 'paused'
        campaign.save()
        
        # Update reel
        campaign.reel.is_boosted = False
        campaign.reel.save()
        
        return Response({'success': True})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resume_boost_campaign(request, campaign_id):
    """Resume a paused boost campaign"""
    try:
        user = request.user
        campaign = get_object_or_404(BoostCampaign, id=campaign_id, user=user)
        
        if campaign.status != 'paused':
            return Response({'error': 'Campaign is not paused'}, status=400)
        
        if timezone.now() >= campaign.end_time:
            return Response({'error': 'Campaign has expired'}, status=400)
        
        campaign.status = 'active'
        campaign.save()
        
        # Update reel
        campaign.reel.is_boosted = True
        campaign.reel.active_boost_campaign = campaign
        campaign.reel.save()
        
        return Response({'success': True})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_eligible_boosts(request):
    """Get boosted posts eligible for the current user's feed"""
    try:
        user = request.user
        profile = user.profile
        
        # Get active campaigns with remaining budget
        now = timezone.now()
        eligible_campaigns = BoostCampaign.objects.filter(
            status='active',
            end_time__gt=now,
            coins_remaining__gt=0
        ).select_related('reel', 'reel__user').prefetch_related('impressions')
        
        # Filter by targeting and frequency capping
        filtered_campaigns = []
        for campaign in eligible_campaigns:
            # Skip if user is the post owner
            if campaign.reel.user == user:
                continue
            
            # Check if user already follows (boosts are for non-followers)
            from .models import Follow
            is_follower = Follow.objects.filter(
                follower=user,
                following=campaign.reel.user
            ).exists()
            if is_follower:
                continue
            
            # Check targeting
            if campaign.target_gender and campaign.target_gender != 'all':
                if profile.gender != campaign.target_gender:
                    continue
            
            if campaign.target_age_min and profile.age < campaign.target_age_min:
                continue
            
            if campaign.target_age_max and profile.age > campaign.target_age_max:
                continue
            
            if campaign.target_location and profile.city != campaign.target_location:
                continue
            
            # Check frequency capping
            config = BoostConfig.objects.first()
            if config:
                last_view = BoostImpression.objects.filter(
                    campaign=campaign,
                    viewer=user,
                    viewed_at__gte=now - timedelta(hours=config.frequency_cap_hours)
                ).exists()
                if last_view:
                    continue
            
            filtered_campaigns.append(campaign)
        
        # Return reel IDs for feed injection
        reel_ids = [campaign.reel.id for campaign in filtered_campaigns]
        
        return Response({
            'eligible_reel_ids': reel_ids,
            'count': len(reel_ids),
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_boost_impression(request):
    """Record that a user viewed a boosted post"""
    try:
        user = request.user
        reel_id = request.data.get('reel_id')
        
        # Find active campaign for this reel
        campaign = BoostCampaign.objects.filter(
            reel_id=reel_id,
            status='active',
            end_time__gt=timezone.now(),
            coins_remaining__gt=0
        ).first()
        
        if not campaign:
            return Response({'success': False, 'message': 'No active campaign'})
        
        # Check frequency cap
        config = BoostConfig.objects.first()
        if config:
            last_view = BoostImpression.objects.filter(
                campaign=campaign,
                viewer=user,
                viewed_at__gte=timezone.now() - timedelta(hours=config.frequency_cap_hours)
            ).exists()
            if last_view:
                return Response({'success': False, 'message': 'Frequency cap reached'})
        
        # Record impression
        impression, created = BoostImpression.objects.get_or_create(
            campaign=campaign,
            viewer=user
        )
        
        if created:
            # Update campaign stats
            campaign.impressions_served += 1
            
            # Deduct coins based on pacing
            coins_to_deduct = campaign.hourly_budget / config.base_impression_rate if config else Decimal('1')
            if campaign.coins_remaining >= coins_to_deduct:
                campaign.coins_remaining -= coins_to_deduct
            else:
                campaign.coins_remaining = Decimal('0')
                campaign.status = 'exhausted'
            
            campaign.save()
            
            # Update reel stats
            campaign.reel.total_boost_impressions += 1
            campaign.reel.save()
        
        return Response({'success': True})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_boost_engagement(request):
    """Record engagement on a boosted post"""
    try:
        user = request.user
        reel_id = request.data.get('reel_id')
        engagement_type = request.data.get('engagement_type')  # 'like', 'comment', 'share'
        
        # Find active campaign for this reel
        campaign = BoostCampaign.objects.filter(
            reel_id=reel_id,
            status='active',
            end_time__gt=timezone.now()
        ).first()
        
        if not campaign:
            return Response({'success': False, 'message': 'No active campaign'})
        
        # Record engagement
        engagement, created = BoostEngagement.objects.get_or_create(
            campaign=campaign,
            user=user,
            engagement_type=engagement_type
        )
        
        if created:
            # Update campaign stats
            campaign.engagement_count += 1
            campaign.save()
            
            # Update reel stats
            campaign.reel.total_boost_engagements += 1
            campaign.reel.save()
        
        return Response({'success': True})
    except Exception as e:
        return Response({'error': str(e)}, status=500)
