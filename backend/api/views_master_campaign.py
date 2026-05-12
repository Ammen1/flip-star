from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta, datetime
import calendar

from .models_master_campaign import MasterCampaign, MasterCampaignParticipant
from .serializers_master_campaign import MasterCampaignSerializer, MasterCampaignParticipantSerializer
from .models_campaign import Campaign

@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def master_campaign_list(request):
    """List all master campaigns or create a new one"""
    if request.method == 'GET':
        campaigns = MasterCampaign.objects.all().order_by('-created_at')
        serializer = MasterCampaignSerializer(campaigns, many=True)
        return Response({'master_campaigns': serializer.data})
    
    elif request.method == 'POST':
        serializer = MasterCampaignSerializer(data=request.data)
        if serializer.is_valid():
            # Set created_by to current user
            serializer.save(created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAdminUser])
def master_campaign_detail(request, pk):
    """Get, update or delete a specific master campaign"""
    try:
        campaign = MasterCampaign.objects.get(pk=pk)
    except MasterCampaign.DoesNotExist:
        return Response({'error': 'Master campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        serializer = MasterCampaignSerializer(campaign)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = MasterCampaignSerializer(campaign, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        campaign.delete()
        return Response({'message': 'Master campaign deleted successfully'})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def master_campaign_participants(request, pk):
    """Get participants of a specific master campaign"""
    try:
        campaign = MasterCampaign.objects.get(pk=pk)
        participants = campaign.participants.all().order_by('-total_score')
        serializer = MasterCampaignParticipantSerializer(participants, many=True)
        return Response({'participants': serializer.data})
    except MasterCampaign.DoesNotExist:
        return Response({'error': 'Master campaign not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def join_master_campaign(request, pk):
    """Join a master campaign"""
    try:
        campaign = MasterCampaign.objects.get(pk=pk)
        
        # Check if campaign is active or upcoming
        if not (campaign.is_active() or campaign.is_upcoming()):
            return Response({'error': 'Cannot join this campaign'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if already joined
        if campaign.participants.filter(user=request.user).exists():
            return Response({'error': 'Already joined this campaign'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check entry requirements
        if campaign.min_followers > 0:
            # This would need to be implemented based on your follower counting logic
            pass
        
        if campaign.min_level > request.user.profile.level:
            return Response({'error': f'Minimum level {campaign.min_level} required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create participant
        participant = MasterCampaignParticipant.objects.create(
            master_campaign=campaign,
            user=request.user
        )
        
        # Update campaign stats
        campaign.total_participants += 1
        campaign.save()
        
        serializer = MasterCampaignParticipantSerializer(participant)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except MasterCampaign.DoesNotExist:
        return Response({'error': 'Master campaign not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def master_campaign_stats(request, pk):
    """Get detailed statistics for a master campaign"""
    try:
        campaign = MasterCampaign.objects.get(pk=pk)
        print(f"[MASTER_CAMPAIGN_STATS] Getting stats for campaign {pk}: {campaign.title}")
        
        # Get sub-campaigns stats
        sub_campaigns = campaign.sub_campaigns.all()
        print(f"[MASTER_CAMPAIGN_STATS] Found {sub_campaigns.count()} total sub-campaigns")
        
        # Debug: Print all sub-campaigns
        for sub in sub_campaigns:
            print(f"[MASTER_CAMPAIGN_STATS] Sub-campaign: {sub.title} - Type: {sub.campaign_type}")
        
        campaign_stats = {
            'daily': sub_campaigns.filter(campaign_type='daily').count(),
            'weekly': sub_campaigns.filter(campaign_type='weekly').count(),
            'monthly': sub_campaigns.filter(campaign_type='monthly').count(),
            'grand': sub_campaigns.filter(campaign_type='grand').count(),
        }
        
        print(f"[MASTER_CAMPAIGN_STATS] Campaign stats: {campaign_stats}")
        
        # Get participant stats
        participants = campaign.participants.all()
        participant_stats = {
            'total': participants.count(),
            'active': participants.filter(is_active=True).count(),
            'top_performers': participants.order_by('-total_score')[:10].values(
                'user__username', 'total_score', 'total_posts'
            )
        }
        
        # Get recent activity
        recent_campaigns = sub_campaigns.order_by('-created_at')[:5]
        recent_serializer = MasterCampaignSerializer(recent_campaigns, many=True)
        
        return Response({
            'campaign': MasterCampaignSerializer(campaign).data,
            'campaign_stats': campaign_stats,
            'participant_stats': participant_stats,
            'recent_campaigns': recent_serializer.data
        })
        
    except MasterCampaign.DoesNotExist:
        return Response({'error': 'Master campaign not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def test_generate_endpoint(request, pk):
    """Test endpoint to verify CORS and basic functionality"""
    try:
        print(f"[TEST] Test endpoint called for campaign {pk}")
        return Response({
            'message': 'Test endpoint working',
            'campaign_id': pk,
            'timestamp': timezone.now().isoformat()
        })
    except Exception as e:
        print(f"[TEST] Test endpoint error: {str(e)}")
        return Response({
            'error': 'Test endpoint failed',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT'])
@permission_classes([IsAdminUser])
def update_generation_config(request, pk):
    """Update generation configuration for a master campaign"""
    try:
        campaign = MasterCampaign.objects.get(pk=pk)
        
        # Update configuration fields
        if 'daily_campaign_count' in request.data:
            campaign.daily_campaign_count = request.data['daily_campaign_count']
        if 'weekly_campaign_count' in request.data:
            campaign.weekly_campaign_count = request.data['weekly_campaign_count']
        if 'monthly_campaign_count' in request.data:
            campaign.monthly_campaign_count = request.data['monthly_campaign_count']
        if 'grand_campaign_count' in request.data:
            campaign.grand_campaign_count = request.data['grand_campaign_count']
        
        # Update auto-generation flags
        if 'auto_generate_daily' in request.data:
            campaign.auto_generate_daily = request.data['auto_generate_daily']
        if 'auto_generate_weekly' in request.data:
            campaign.auto_generate_weekly = request.data['auto_generate_weekly']
        if 'auto_generate_monthly' in request.data:
            campaign.auto_generate_monthly = request.data['auto_generate_monthly']
        if 'auto_generate_grand' in request.data:
            campaign.auto_generate_grand = request.data['auto_generate_grand']
        
        campaign.save()
        
        from .serializers_master_campaign import MasterCampaignSerializer
        serializer = MasterCampaignSerializer(campaign)
        return Response(serializer.data)
        
    except MasterCampaign.DoesNotExist:
        return Response({'error': 'Master campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def generate_sub_campaigns(request, pk):
    """Generate sub-campaigns for a master campaign"""
    try:
        print(f"[GENERATE_SUB_CAMPAIGNS] Starting generation for master campaign {pk}")
        campaign = MasterCampaign.objects.get(pk=pk)
        print(f"[GENERATE_SUB_CAMPAIGNS] Found campaign: {campaign.title}")
        print(f"[GENERATE_SUB_CAMPAIGNS] Campaign settings:")
        print(f"  - auto_generate_daily: {campaign.auto_generate_daily}")
        print(f"  - auto_generate_weekly: {campaign.auto_generate_weekly}")
        print(f"  - auto_generate_monthly: {campaign.auto_generate_monthly}")
        print(f"  - auto_generate_grand: {campaign.auto_generate_grand}")
        print(f"  - start_date: {campaign.start_date}")
        print(f"  - end_date: {campaign.end_date}")
        print(f"  - status: {campaign.status}")
        print(f"  - min_followers: {campaign.min_followers}")
        print(f"  - min_level: {campaign.min_level}")
        
        if not campaign.start_date or not campaign.end_date:
            print(f"[GENERATE_SUB_CAMPAIGNS] Missing dates: start_date={campaign.start_date}, end_date={campaign.end_date}")
            return Response({'error': 'Master campaign must have start and end dates'}, status=status.HTTP_400_BAD_REQUEST)
        
        generated_campaigns = []
        deleted_campaigns = []
        
        # Check if cleanup is requested
        cleanup_excess = request.data.get('cleanup_excess', False)
        
        # Cleanup excess campaigns if requested
        if cleanup_excess:
            print(f"[GENERATE_SUB_CAMPAIGNS] Cleanup mode enabled")
            
            # Clean up each type
            for campaign_type in ['daily', 'weekly', 'monthly', 'grand']:
                count_field = f'{campaign_type}_campaign_count'
                desired_count = getattr(campaign, count_field, 0)
                
                # Get existing campaigns of this type, ordered by start_date (farthest first for deletion)
                existing = campaign.sub_campaigns.filter(campaign_type=campaign_type).order_by('-start_date')
                current_count = existing.count()
                
                # If we have more than desired, delete the excess (farthest dates first)
                if desired_count > 0 and current_count > desired_count:
                    excess_count = current_count - desired_count
                    campaigns_to_delete = existing[:excess_count]
                    
                    print(f"[GENERATE_SUB_CAMPAIGNS] Deleting {excess_count} excess {campaign_type} campaigns")
                    for camp in campaigns_to_delete:
                        print(f"  - Deleting: {camp.title} (start: {camp.start_date})")
                        deleted_campaigns.append(camp.title)
                        camp.delete()
        
        # Check request data
        print(f"[GENERATE_SUB_CAMPAIGNS] Request data: {request.data}")
        print(f"[GENERATE_SUB_CAMPAIGNS] generate_daily: {request.data.get('generate_daily')}")
        print(f"[GENERATE_SUB_CAMPAIGNS] generate_weekly: {request.data.get('generate_weekly')}")
        print(f"[GENERATE_SUB_CAMPAIGNS] generate_monthly: {request.data.get('generate_monthly')}")
        print(f"[GENERATE_SUB_CAMPAIGNS] generate_grand: {request.data.get('generate_grand')}")
        
        # Generate daily campaigns
        if campaign.auto_generate_daily and request.data.get('generate_daily', True):
            current_date = campaign.start_date.date()
            end_date = campaign.end_date.date()
            today = timezone.now().date()
            
            # Calculate how many to generate
            total_days = (end_date - current_date).days + 1
            daily_count = campaign.daily_campaign_count if campaign.daily_campaign_count > 0 else total_days
            
            print(f"[GENERATE_SUB_CAMPAIGNS] Generating {daily_count} daily campaigns from {current_date} to {end_date} (total days: {total_days})")
            
            # Check if the date range makes sense
            if current_date > end_date:
                print(f"[GENERATE_SUB_CAMPAIGNS] ERROR: Start date {current_date} is after end date {end_date}")
                return Response({'error': 'Start date cannot be after end date'}, status=status.HTTP_400_BAD_REQUEST)
            
            generated_daily = 0
            while current_date <= end_date and generated_daily < daily_count:
                try:
                    # Check if daily campaign already exists
                    if not campaign.sub_campaigns.filter(
                        campaign_type='daily',
                        start_date__date=current_date
                    ).exists():
                        
                        print(f"[GENERATE_SUB_CAMPAIGNS] Creating daily campaign for {current_date}")
                        
                        # Prepare campaign data
                        campaign_data = {
                            'title': f"{campaign.title} - Daily {current_date.strftime('%b %d')}",
                            'description': f"Daily campaign for {current_date.strftime('%B %d, %Y')}",
                            'campaign_type': 'daily',
                            'master_campaign': campaign,
                            'prize_title': "Daily Winner",
                            'prize_description': "Daily campaign winner",
                            'prize_value': 0,  # Add missing prize_value field
                            'min_followers': campaign.min_followers,
                            'min_level': campaign.min_level,
                            'required_hashtags': campaign.required_hashtags,
                            'created_by': request.user
                        }
                        
                        # Handle dates with error checking
                        try:
                            start_datetime = datetime.combine(current_date, datetime.min.time()).replace(hour=0, minute=0)
                            deadline_datetime = datetime.combine(current_date, datetime.min.time()).replace(hour=20, minute=0)
                            voting_start_datetime = datetime.combine(current_date, datetime.min.time()).replace(hour=21, minute=0)
                            voting_end_datetime = datetime.combine(current_date, datetime.min.time()).replace(hour=23, minute=59)
                            
                            campaign_data['start_date'] = timezone.make_aware(start_datetime)
                            campaign_data['entry_deadline'] = timezone.make_aware(deadline_datetime)
                            campaign_data['voting_start'] = timezone.make_aware(voting_start_datetime)
                            campaign_data['voting_end'] = timezone.make_aware(voting_end_datetime)
                            campaign_data['status'] = 'active' if current_date <= timezone.now().date() else 'upcoming'
                            
                            print(f"[GENERATE_SUB_CAMPAIGNS] Campaign data prepared: {campaign_data}")
                        except Exception as date_error:
                            print(f"[GENERATE_SUB_CAMPAIGNS] Date error: {str(date_error)}")
                            import traceback
                            traceback.print_exc()
                            continue
                        
                        # Create campaign
                        try:
                            daily_campaign = Campaign.objects.create(**campaign_data)
                            generated_campaigns.append(daily_campaign)
                            generated_daily += 1
                            print(f"[GENERATE_SUB_CAMPAIGNS] Created daily campaign: {daily_campaign.title} (ID: {daily_campaign.id})")
                        except Exception as create_error:
                            print(f"[GENERATE_SUB_CAMPAIGNS] Campaign creation error: {str(create_error)}")
                            import traceback
                            traceback.print_exc()
                            continue
                        
                        # Verify the campaign was actually saved
                        try:
                            verify_campaign = Campaign.objects.get(id=daily_campaign.id)
                            print(f"[GENERATE_SUB_CAMPAIGNS] Verified campaign exists: {verify_campaign.title}, Master: {verify_campaign.master_campaign}")
                        except Campaign.DoesNotExist:
                            print(f"[GENERATE_SUB_CAMPAIGNS] ERROR: Campaign was not saved properly!")
                    else:
                        print(f"[GENERATE_SUB_CAMPAIGNS] Daily campaign for {current_date} already exists, skipping")
                        generated_daily += 1  # Count existing campaigns too
                    
                    current_date += timedelta(days=1)
                except Exception as e:
                    print(f"[GENERATE_SUB_CAMPAIGNS] Error creating daily campaign for {current_date}: {str(e)}")
                    current_date += timedelta(days=1)
                    continue
        
        # Generate weekly campaigns
        if campaign.auto_generate_weekly and request.data.get('generate_weekly', True):
            current_date = campaign.start_date.date()
            end_date = campaign.end_date.date()
            
            # Calculate how many weeks
            total_weeks = ((end_date - current_date).days // 7) + 1
            weekly_count = campaign.weekly_campaign_count if campaign.weekly_campaign_count > 0 else total_weeks
            
            print(f"[GENERATE_SUB_CAMPAIGNS] Generating {weekly_count} weekly campaigns (total weeks: {total_weeks})")
            
            generated_weekly = 0
            week_start = current_date
            while week_start <= end_date and generated_weekly < weekly_count:
                week_end = min(week_start + timedelta(days=6), end_date)
                
                if not campaign.sub_campaigns.filter(
                    campaign_type='weekly',
                    start_date__date=week_start
                ).exists():
                    try:
                        weekly_campaign = Campaign.objects.create(
                            title=f"{campaign.title} - Week {generated_weekly + 1}",
                            description=f"Weekly campaign {week_start.strftime('%b %d')} - {week_end.strftime('%b %d')}",
                            campaign_type='weekly',
                            master_campaign=campaign,
                            prize_title="Weekly Winner",
                            prize_description="Weekly campaign winner",
                            prize_value=0,
                            min_followers=campaign.min_followers,
                            min_level=campaign.min_level,
                            required_hashtags=campaign.required_hashtags,
                            start_date=timezone.make_aware(datetime.combine(week_start, datetime.min.time())),
                            entry_deadline=timezone.make_aware(datetime.combine(week_end, datetime.min.time()).replace(hour=20)),
                            voting_start=timezone.make_aware(datetime.combine(week_end, datetime.min.time()).replace(hour=21)),
                            voting_end=timezone.make_aware(datetime.combine(week_end, datetime.min.time()).replace(hour=23, minute=59)),
                            status='active' if week_start <= timezone.now().date() else 'upcoming',
                            created_by=request.user
                        )
                        generated_campaigns.append(weekly_campaign)
                        generated_weekly += 1
                        print(f"[GENERATE_SUB_CAMPAIGNS] Created weekly campaign: {weekly_campaign.title}")
                    except Exception as e:
                        print(f"[GENERATE_SUB_CAMPAIGNS] Error creating weekly campaign: {str(e)}")
                else:
                    generated_weekly += 1
                    print(f"[GENERATE_SUB_CAMPAIGNS] Weekly campaign for {week_start} already exists")
                
                week_start += timedelta(days=7)
        
        # Generate monthly campaigns
        if campaign.auto_generate_monthly and request.data.get('generate_monthly', True):
            current_date = campaign.start_date.date()
            end_date = campaign.end_date.date()
            
            # Calculate how many months
            months_diff = (end_date.year - current_date.year) * 12 + (end_date.month - current_date.month) + 1
            monthly_count = campaign.monthly_campaign_count if campaign.monthly_campaign_count > 0 else months_diff
            
            print(f"[GENERATE_SUB_CAMPAIGNS] Generating {monthly_count} monthly campaigns (total months: {months_diff})")
            
            generated_monthly = 0
            month_start = current_date.replace(day=1)
            while month_start <= end_date and generated_monthly < monthly_count:
                # Get last day of month using calendar module
                last_day = calendar.monthrange(month_start.year, month_start.month)[1]
                month_end = month_start.replace(day=last_day)
                
                month_end = min(month_end, end_date)
                
                if not campaign.sub_campaigns.filter(
                    campaign_type='monthly',
                    start_date__date=month_start
                ).exists():
                    try:
                        monthly_campaign = Campaign.objects.create(
                            title=f"{campaign.title} - {month_start.strftime('%B %Y')}",
                            description=f"Monthly campaign for {month_start.strftime('%B %Y')}",
                            campaign_type='monthly',
                            master_campaign=campaign,
                            prize_title="Monthly Winner",
                            prize_description="Monthly campaign winner",
                            prize_value=0,
                            min_followers=campaign.min_followers,
                            min_level=campaign.min_level,
                            required_hashtags=campaign.required_hashtags,
                            start_date=timezone.make_aware(datetime.combine(month_start, datetime.min.time())),
                            entry_deadline=timezone.make_aware(datetime.combine(month_end, datetime.min.time()).replace(hour=20)),
                            voting_start=timezone.make_aware(datetime.combine(month_end, datetime.min.time()).replace(hour=21)),
                            voting_end=timezone.make_aware(datetime.combine(month_end, datetime.min.time()).replace(hour=23, minute=59)),
                            status='active' if month_start <= timezone.now().date() else 'upcoming',
                            created_by=request.user
                        )
                        generated_campaigns.append(monthly_campaign)
                        generated_monthly += 1
                        print(f"[GENERATE_SUB_CAMPAIGNS] Created monthly campaign: {monthly_campaign.title}")
                    except Exception as e:
                        print(f"[GENERATE_SUB_CAMPAIGNS] Error creating monthly campaign: {str(e)}")
                else:
                    generated_monthly += 1
                    print(f"[GENERATE_SUB_CAMPAIGNS] Monthly campaign for {month_start} already exists")
                
                # Move to next month
                if month_start.month == 12:
                    month_start = month_start.replace(year=month_start.year + 1, month=1, day=1)
                else:
                    month_start = month_start.replace(month=month_start.month + 1, day=1)
        
        # Generate grand campaign
        if campaign.auto_generate_grand and request.data.get('generate_grand', True):
            try:
                if not campaign.sub_campaigns.filter(campaign_type='grand').exists():
                    print(f"[GENERATE_SUB_CAMPAIGNS] Creating grand campaign")
                    grand_campaign = Campaign.objects.create(
                        title=f"{campaign.title} - Grand Finale",
                        description=f"Grand campaign finale for {campaign.title}",
                        campaign_type='grand',
                        master_campaign=campaign,
                        start_date=campaign.end_date - timedelta(days=7),
                        entry_deadline=campaign.end_date - timedelta(days=3),
                        voting_start=campaign.end_date - timedelta(days=3),
                        voting_end=campaign.end_date,
                        status='upcoming',
                        prize_title="Grand Champion",
                        prize_description="Ultimate winner of the season",
                        prize_value=0,  # Add missing prize_value field
                        min_followers=campaign.min_followers,
                        min_level=campaign.min_level,
                        required_hashtags=campaign.required_hashtags,
                        created_by=request.user
                    )
                    generated_campaigns.append(grand_campaign)
                    print(f"[GENERATE_SUB_CAMPAIGNS] Created grand campaign: {grand_campaign.title}")
                else:
                    print(f"[GENERATE_SUB_CAMPAIGNS] Grand campaign already exists, skipping")
            except Exception as e:
                print(f"[GENERATE_SUB_CAMPAIGNS] Error creating grand campaign: {str(e)}")
        
        # Update campaign stats
        try:
            campaign.total_daily_campaigns = campaign.sub_campaigns.filter(campaign_type='daily').count()
            campaign.total_weekly_campaigns = campaign.sub_campaigns.filter(campaign_type='weekly').count()
            campaign.total_monthly_campaigns = campaign.sub_campaigns.filter(campaign_type='monthly').count()
            campaign.total_grand_campaigns = campaign.sub_campaigns.filter(campaign_type='grand').count()
            campaign.save()
            print(f"[GENERATE_SUB_CAMPAIGNS] Updated campaign stats")
        except Exception as e:
            print(f"[GENERATE_SUB_CAMPAIGNS] Error updating stats: {str(e)}")
        
        print(f"[GENERATE_SUB_CAMPAIGNS] Successfully generated {len(generated_campaigns)} sub-campaigns")
        
        # Build response message
        message_parts = []
        if len(deleted_campaigns) > 0:
            message_parts.append(f'Deleted {len(deleted_campaigns)} excess campaigns')
        if len(generated_campaigns) > 0:
            message_parts.append(f'Generated {len(generated_campaigns)} new campaigns')
        if not message_parts:
            message_parts.append('No changes needed - campaigns already match configuration')
        
        return Response({
            'message': ' | '.join(message_parts),
            'campaigns': [c.title for c in generated_campaigns],
            'deleted': deleted_campaigns,
            'generated_count': len(generated_campaigns),
            'deleted_count': len(deleted_campaigns)
        })
        
    except MasterCampaign.DoesNotExist:
        print(f"[GENERATE_SUB_CAMPAIGNS] Master campaign {pk} not found")
        return Response({'error': 'Master campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"[GENERATE_SUB_CAMPAIGNS] Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'error': 'Internal server error while generating sub-campaigns',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
