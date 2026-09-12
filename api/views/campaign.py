from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from api.models import Follow, MediaStatus, Reel
from api.models.campaign import (
    Campaign,
    CampaignEntry,
    CampaignNotification,
    CampaignVote,
    CampaignWinner,
)
from api.models.campaign_extended import PostScore, UserCampaignStats
from api.services.realms import RealmValidationError, organization_for_new_campaign
from common.permissions.realms import CanCreateCampaign
from common.security import encrypted_endpoint


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
        return f'https://postworq.onrender.com{url}'
    except (AttributeError, ValueError):
        # An unset field or a storage backend that cannot build a URL. An image
        # is decoration on a campaign card; neither should fail the response.
        return None


# Admin Campaign Management
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_campaigns_list(request):
    """Get all campaigns for admin"""
    print(f'[CAMPAIGN LIST] User: {request.user}, Is Staff: {request.user.is_staff}')
    campaigns = Campaign.objects.all().order_by('-created_at')
    print(f'[CAMPAIGN LIST] Total campaigns: {campaigns.count()}')

    # Filters
    status_filter = request.GET.get('status')
    if status_filter:
        campaigns = campaigns.filter(status=status_filter)

    master_campaign_filter = request.GET.get('master_campaign')
    if master_campaign_filter:
        campaigns = campaigns.filter(master_campaign_id=master_campaign_filter)

    # Annotate with live counts from the database
    campaigns = campaigns.annotate(
        live_entries=Count('entries', distinct=True),
        live_votes=Sum('entries__vote_count'),
    )

    # Pagination
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    start = (page - 1) * page_size
    end = start + page_size

    total = campaigns.count()
    campaigns_page = campaigns[start:end]

    data = []
    for c in campaigns_page:
        image_url = get_image_url(c.image, request)

        data.append(
            {
                'id': c.id,
                'title': c.title,
                'description': c.description,
                'campaign_type': c.campaign_type,
                'image': image_url,
                'prize_title': c.prize_title,
                'prize_value': str(c.prize_value),
                'status': c.status,
                'start_date': c.start_date,
                'entry_deadline': c.entry_deadline,
                'voting_start': c.voting_start,
                'voting_end': c.voting_end,
                'total_entries': c.live_entries or 0,
                'total_votes': c.live_votes or 0,
                'winner_count': c.winner_count,
                'winners_announced': c.winners_announced,
                'created_at': c.created_at,
            }
        )

    return Response(
        {
            'campaigns': data,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
        }
    )


@api_view(['POST'])
@permission_classes([CanCreateCampaign])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_campaign_create(request):
    """Create a campaign, owned by the creator's organization.

    Ownership is derived from the authenticated account and never read from
    the request. A body carrying `organization` or `organization_id` does not
    fail -- the field simply has no effect, because nothing here reads it. That
    is what stops an organization user creating a campaign under a different
    organization.
    """
    try:
        # The owner, decided by who is asking. None means a platform campaign,
        # which is what a Flipstar-created campaign is.
        try:
            # The requested id is consulted only for platform staff; for an
            # organization user the service ignores it and returns their own.
            owning_organization = organization_for_new_campaign(
                request.user,
                requested_organization_id=(
                    request.data.get('organization') or request.data.get('organization_id')
                ),
            )
        except RealmValidationError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        print('=== Campaign Creation Debug ===')
        print('request.data keys:', request.data.keys())
        print('request.FILES keys:', request.FILES.keys())
        print('Has image in FILES:', 'image' in request.FILES)

        # Convert empty date strings to None
        start_date = request.data.get('start_date') or None
        entry_deadline = request.data.get('entry_deadline') or None
        voting_start = request.data.get('voting_start') or None
        voting_end = request.data.get('voting_end') or None

        campaign = Campaign.objects.create(
            title=request.data.get('title'),
            description=request.data.get('description'),
            campaign_type=request.data.get('campaign_type', 'grand'),
            master_campaign_id=request.data.get('master_campaign'),
            prize_title=request.data.get('prize_title'),
            prize_description=request.data.get('prize_description'),
            prize_value=request.data.get('prize_value', 0),
            status=request.data.get('status', 'draft'),
            min_followers=request.data.get('min_followers', 0),
            min_level=request.data.get('min_level', 1),
            min_votes_per_reel=request.data.get('min_votes_per_reel', 0),
            required_hashtags=request.data.get('required_hashtags', ''),
            start_date=start_date,
            entry_deadline=entry_deadline,
            voting_start=voting_start,
            voting_end=voting_end,
            winner_count=request.data.get('winner_count', 1),
            created_by=request.user,
            # From the account, not from request.data.
            organization=owning_organization,
        )

        # Handle image upload
        if 'image' in request.FILES:
            print('Image file found:', request.FILES['image'].name)
            campaign.image = request.FILES['image']
            campaign.save()
            print('Image saved to:', campaign.image.name)
        else:
            print('No image file in request.FILES')

        # Notify eligible users if campaign is active
        if campaign.status == 'active':
            notify_eligible_users(campaign)

        return Response(
            {
                'id': campaign.id,
                'message': 'Campaign created successfully',
                'image_url': campaign.image.url if campaign.image else None,
            },
            status=status.HTTP_201_CREATED,
        )
    except Exception as e:
        print('Error creating campaign:', str(e))
        import traceback

        traceback.print_exc()
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH'])
@permission_classes([IsAdminUser])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_campaign_update(request, campaign_id):
    """Update campaign"""
    print(f'[UPDATE] Campaign ID: {campaign_id}, User: {request.user}, Method: {request.method}')
    print(f"[UPDATE] Auth header: {request.headers.get('Authorization', 'None')[:20]}...")

    try:
        campaign = Campaign.objects.get(id=campaign_id)
        print(f'[UPDATE] Found campaign: {campaign.title}')

        for field in [
            'title',
            'description',
            'prize_title',
            'prize_description',
            'prize_value',
            'status',
            'campaign_type',
            'min_followers',
            'min_level',
            'min_votes_per_reel',
            'required_hashtags',
            'start_date',
            'entry_deadline',
            'voting_start',
            'voting_end',
            'winner_count',
        ]:
            if field in request.data:
                setattr(campaign, field, request.data[field])
                print(f'[UPDATE] Set {field}: {request.data[field]}')

        # Handle image upload
        if 'image' in request.FILES:
            print(f"[UPDATE] Image file: {request.FILES['image'].name}")
            campaign.image = request.FILES['image']

        campaign.save()
        print(f'[UPDATE] Campaign {campaign_id} saved successfully')

        # If status changed to voting, notify participants
        if request.data.get('status') == 'voting':
            notify_voting_started(campaign)

        return Response({'message': 'Campaign updated successfully'})
    except Campaign.DoesNotExist:
        print(f'[UPDATE] Campaign {campaign_id} NOT FOUND in database')
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f'[UPDATE] ERROR: {str(e)}')
        import traceback

        traceback.print_exc()
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def admin_campaign_delete(request, campaign_id):
    """Delete campaign"""
    print(f'[DELETE] Campaign ID: {campaign_id}, User: {request.user}, Method: {request.method}')
    print(f"[DELETE] Auth header: {request.headers.get('Authorization', 'None')[:20]}...")

    try:
        campaign = Campaign.objects.get(id=campaign_id)
        print(f'[DELETE] Found campaign: {campaign.title}, deleting...')
        campaign.delete()
        print(f'[DELETE] Campaign {campaign_id} deleted successfully')
        return Response({'message': 'Campaign deleted successfully'})
    except Campaign.DoesNotExist:
        print(f'[DELETE] Campaign {campaign_id} NOT FOUND in database')
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f'[DELETE] ERROR: {str(e)}')
        import traceback

        traceback.print_exc()
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_campaign_entries(request, campaign_id):
    """Get all entries for a campaign"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        entries = CampaignEntry.objects.filter(campaign=campaign).select_related('user', 'reel')

        data = [
            {
                'id': entry.id,
                'user': {
                    'id': entry.user.id,
                    'username': entry.user.username,
                },
                'reel': {
                    'id': entry.reel.id,
                    'caption': entry.reel.caption,
                    'image': request.build_absolute_uri(entry.reel.image.url)
                    if entry.reel.image
                    else None,
                },
                'vote_count': entry.vote_count,
                'rank': entry.rank,
                'is_winner': entry.is_winner,
                'approved': entry.approved,
                'disqualified': entry.disqualified,
                'submitted_at': entry.submitted_at,
            }
            for entry in entries
        ]

        return Response(data)
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_announce_winners(request, campaign_id):
    """Announce winners for a campaign.

    Guarded end-to-end by a short transaction holding a row lock on the
    Campaign: two concurrent calls for the same campaign (e.g. an admin
    double-clicking, or a retried request) must announce winners and send
    notifications exactly once. No external API calls happen inside this
    transaction, so holding the lock for the whole batch is safe and stays
    short.
    """
    try:
        with transaction.atomic():
            campaign = Campaign.objects.select_for_update().get(id=campaign_id)

            if campaign.winners_announced:
                return Response(
                    {'error': 'Winners have already been announced for this campaign'},
                    status=status.HTTP_409_CONFLICT,
                )

            # Get top entries by vote count
            top_entries = list(
                CampaignEntry.objects.filter(
                    campaign=campaign, approved=True, disqualified=False
                ).order_by('-vote_count')[: campaign.winner_count]
            )

            # Create winners
            for rank, entry in enumerate(top_entries, 1):
                winner, created = CampaignWinner.objects.get_or_create(
                    campaign=campaign, rank=rank, defaults={'entry': entry, 'user': entry.user}
                )
                entry.is_winner = True
                entry.rank = rank
                entry.save()

                # Notify winner
                CampaignNotification.objects.create(
                    campaign=campaign,
                    user=entry.user,
                    notification_type='winner_announced',
                    message=f'Congratulations! You won {rank} place in {campaign.title}!',
                )

            campaign.winners_announced = True
            campaign.status = 'completed'
            campaign.save()

        return Response({'message': f'{len(top_entries)} winners announced successfully'})
    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)


# User Campaign APIs
@api_view(['GET'])
@encrypted_endpoint
def user_campaigns_list(request):
    """Get active campaigns for users (public endpoint)"""
    now = timezone.now()

    # Get status filter from query params
    status_filter = request.GET.get('status', 'all')

    if status_filter == 'active':
        campaigns = Campaign.objects.filter(status='active').order_by('-created_at')
    elif status_filter == 'voting':
        campaigns = Campaign.objects.filter(status='voting').order_by('-created_at')
    elif status_filter == 'upcoming':
        campaigns = Campaign.objects.filter(status='draft', start_date__gt=now).order_by(
            'start_date'
        )
    elif status_filter == 'completed':
        campaigns = Campaign.objects.filter(status='completed').order_by('-voting_end')
    elif status_filter == 'draft':
        campaigns = Campaign.objects.filter(status='draft').order_by('-created_at')
    else:
        # 'all' or any unknown value — show everything except cancelled
        campaigns = Campaign.objects.exclude(status='cancelled').order_by('-created_at')

    # Annotate with live counts
    campaigns = list(
        campaigns.annotate(
            live_entries=Count('entries', distinct=True),
            live_votes=Sum('entries__vote_count'),
        )
    )

    # Check if user is authenticated
    is_authenticated = request.user and request.user.is_authenticated
    user = request.user if is_authenticated else None
    user_profile = user.profile if (user and hasattr(user, 'profile')) else None
    follower_count = Follow.objects.filter(following=user).count() if user else 0

    # Bulk-check entered campaigns for this user to avoid N+1
    entered_ids = set()
    if is_authenticated and campaigns:
        entered_ids = set(
            CampaignEntry.objects.filter(
                user=user, campaign_id__in=[c.id for c in campaigns]
            ).values_list('campaign_id', flat=True)
        )

    # Compute now once for all is_active / is_voting_open checks
    now = timezone.now()

    data = []
    for c in campaigns:
        # Check if user is eligible (only if authenticated)
        is_eligible = True
        if is_authenticated:
            if c.min_followers > 0 and follower_count < c.min_followers:
                is_eligible = False
            if user_profile and c.min_level > user_profile.level:
                is_eligible = False

        # Inline is_active / is_voting_open without extra now() calls
        c_is_active = (
            c.status == 'active'
            and c.start_date
            and c.entry_deadline
            and c.start_date <= now <= c.entry_deadline
        )
        c_is_voting = (
            c.status == 'voting'
            and c.voting_start
            and c.voting_end
            and c.voting_start <= now <= c.voting_end
        )

        image_url = get_image_url(c.image, request)

        data.append(
            {
                'id': c.id,
                'title': c.title,
                'description': c.description,
                'campaign_type': c.campaign_type,
                'image': image_url,
                'prize_title': c.prize_title,
                'prize_value': str(c.prize_value),
                'status': c.status,
                'start_date': c.start_date,
                'entry_deadline': c.entry_deadline,
                'voting_start': c.voting_start,
                'voting_end': c.voting_end,
                'total_entries': c.live_entries or 0,
                'total_votes': c.live_votes or 0,
                'is_eligible': is_eligible,
                'has_entered': c.id in entered_ids,
                'is_active': c_is_active,
                'is_voting_open': c_is_voting,
            }
        )

    return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def user_campaign_enter(request, campaign_id):
    """Enter a campaign with a reel"""
    print(f'[CAMPAIGN ENTER] Campaign ID: {campaign_id}, User: {request.user}')
    print(f'[CAMPAIGN ENTER] Request data: {request.data}')

    try:
        campaign = Campaign.objects.get(id=campaign_id)
        user = request.user
        reel_id = request.data.get('reel_id')

        print(f'[CAMPAIGN ENTER] Campaign: {campaign.title}, Status: {campaign.status}')
        print(f'[CAMPAIGN ENTER] Reel ID: {reel_id}')

        # Check if campaign accepts entries (active or voting status)
        if campaign.status not in ('active', 'voting'):
            print(f'[CAMPAIGN ENTER] Campaign not active (status={campaign.status})')
            return Response(
                {'error': 'Campaign is not accepting entries'}, status=status.HTTP_400_BAD_REQUEST
            )

        # Get reel
        try:
            reel = Reel.objects.get(id=reel_id, user=user)
            print(f'[CAMPAIGN ENTER] Found reel: {reel.id}')
        except Reel.DoesNotExist:
            print(f'[CAMPAIGN ENTER] Reel {reel_id} not found for user {user.username}')
            return Response({'error': 'Reel not found'}, status=status.HTTP_404_NOT_FOUND)

        # Check eligibility
        user_profile = user.profile if hasattr(user, 'profile') else None
        follower_count = Follow.objects.filter(following=user).count()

        if campaign.min_followers > 0 and follower_count < campaign.min_followers:
            return Response(
                {'error': f'You need at least {campaign.min_followers} followers'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user_profile and campaign.min_level > user_profile.level:
            return Response(
                {'error': f'You need to be level {campaign.min_level}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if campaign.min_votes_per_reel > 0 and reel.votes < campaign.min_votes_per_reel:
            return Response(
                {'error': f'Reel needs at least {campaign.min_votes_per_reel} votes'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create entry (one per user per campaign).
        #
        # get_or_create, not exists()-then-create. The check and the insert were
        # two statements, so two taps on Join both saw no entry and both tried
        # to create one -- CampaignEntry's unique_together caught the duplicate,
        # but as an unhandled IntegrityError, i.e. a 500 on an action that had
        # in fact already succeeded. get_or_create handles that collision and
        # reports the existing row instead.
        entry, created = CampaignEntry.objects.get_or_create(
            campaign=campaign, user=user, defaults={'reel': reel}
        )
        if created:
            # F(), not `campaign.total_entries += 1; campaign.save()`: two
            # concurrent joins both read the same count and one increment was
            # lost, so the campaign under-reported its own entrants.
            Campaign.objects.filter(pk=campaign.pk).update(total_entries=F('total_entries') + 1)
            campaign.refresh_from_db(fields=['total_entries'])
            CampaignNotification.objects.create(
                campaign=campaign,
                user=user,
                notification_type='entry_approved',
                message=f'Your entry to {campaign.title} has been approved!',
            )
            print(f'[CAMPAIGN ENTER] Entry created: {entry.id}')
        else:
            print(f'[CAMPAIGN ENTER] Existing entry reused: {entry.id}')

        # Bridge to new PostScore system so post appears in feed
        post_score_id = None
        try:
            active_theme = campaign.themes.filter(is_active=True).first()

            # Mark reel as campaign post using attnames for FK fields
            reel.campaign_id = campaign.pk
            reel.theme_id = active_theme.pk if active_theme else None
            reel.is_campaign_post = True
            reel.save(update_fields=['campaign_id', 'theme_id', 'is_campaign_post'])

            # Create PostScore (auto-approved so it appears in feed immediately)
            post_score, ps_created = PostScore.objects.get_or_create(
                reel=reel,
                defaults={
                    'campaign': campaign,
                    'theme': active_theme,
                    'user': user,
                    'moderation_status': 'approved',
                },
            )
            if not ps_created and post_score.moderation_status != 'approved':
                post_score.moderation_status = 'approved'
                post_score.save(update_fields=['moderation_status'])

            # Update user campaign stats
            stats, _ = UserCampaignStats.objects.get_or_create(user=user, campaign=campaign)
            stats.total_posts = PostScore.objects.filter(user=user, campaign=campaign).count()
            stats.approved_posts = PostScore.objects.filter(
                user=user, campaign=campaign, moderation_status='approved'
            ).count()
            stats.save(update_fields=['total_posts', 'approved_posts'])

            post_score_id = post_score.id
            print(
                f'[CAMPAIGN ENTER] PostScore id={post_score_id}, approved={post_score.moderation_status}'
            )
        except Exception as bridge_err:
            import traceback

            print(f'[CAMPAIGN ENTER] PostScore bridge error (entry still created): {bridge_err}')
            traceback.print_exc()

        return Response(
            {
                'message': 'Successfully entered campaign',
                'entry_id': entry.id,
                'post_score_id': post_score_id,
            },
            status=status.HTTP_201_CREATED,
        )

    except Campaign.DoesNotExist:
        print(f'[CAMPAIGN ENTER] Campaign {campaign_id} not found')
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f'[CAMPAIGN ENTER] ERROR: {str(e)}')
        import traceback

        traceback.print_exc()
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def user_campaign_vote(request, entry_id):
    """Vote for a campaign entry"""
    try:
        entry = CampaignEntry.objects.get(id=entry_id)
        user = request.user

        # Check if voting is open
        if not entry.campaign.is_voting_open():
            return Response(
                {'error': 'Voting is not open for this campaign'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # One vote per user per entry.
        #
        # exists()-then-create left a window between the two statements.
        # CampaignVote's unique_together closed it at the database, but as an
        # unhandled IntegrityError -- a 500 on a second tap, for a vote that had
        # already been recorded. get_or_create reports the collision instead.
        _, created = CampaignVote.objects.get_or_create(entry=entry, user=user)
        if not created:
            return Response(
                {'error': 'You have already voted for this entry'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Both counters move with F(). They previously read, added and saved in
        # separate statements, so two votes arriving together lost one -- and
        # the bare save() wrote back every other column from a stale snapshot.
        CampaignEntry.objects.filter(pk=entry.pk).update(vote_count=F('vote_count') + 1)
        Campaign.objects.filter(pk=entry.campaign_id).update(total_votes=F('total_votes') + 1)
        entry.refresh_from_db(fields=['vote_count'])
        entry.campaign.refresh_from_db(fields=['total_votes'])

        # Update rankings for all entries in this campaign
        update_campaign_rankings(entry.campaign)

        # Update engagement score in real-time using CampaignScoringConfig
        from api.models.campaign_extended import PostScore

        try:
            post_score = PostScore.objects.filter(reel=entry.reel, campaign=entry.campaign).first()
            if post_score:
                post_score.update_engagement_score()
                print(f'[CAMPAIGN VOTE] Updated engagement score for reel {entry.reel.id}')
        except Exception as e:
            print(f'[CAMPAIGN VOTE] Error updating engagement score: {e}')

        return Response({'message': 'Vote recorded successfully'})

    except CampaignEntry.DoesNotExist:
        return Response({'error': 'Entry not found'}, status=status.HTTP_404_NOT_FOUND)


def _entry_reel(reel, request):
    from api.serializers.core import reel_media_payload

    media = reel_media_payload(reel, request)
    media['thumbnail'] = media['thumbnail'] or media['image']
    return {'id': reel.id, 'caption': reel.caption, **media}


@api_view(['GET'])
@permission_classes([AllowAny])
@encrypted_endpoint
def user_campaign_detail(request, campaign_id):
    """Get campaign details with entries"""
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        is_authenticated = request.user.is_authenticated
        user = request.user if is_authenticated else None

        # An entry whose media is still being encoded (or failed) has nothing
        # to show anyone but its author, who sees its state instead.
        visible = Q(reel__processing_status=MediaStatus.READY)
        if user is not None:
            visible |= Q(user=user)
        entries = list(
            CampaignEntry.objects.filter(campaign=campaign, approved=True, disqualified=False)
            .filter(visible)
            .select_related('user', 'reel')
            .only(
                'id',
                'vote_count',
                'rank',
                'is_winner',
                'user__id',
                'user__username',
                'reel__id',
                'reel__caption',
                'reel__image',
                'reel__media',
                'reel__thumbnail',
                'reel__original_media',
                'reel__original_image',
                'reel__media_360',
                'reel__media_480',
                'reel__image_small',
                'reel__image_medium',
                'reel__image_webp',
                'reel__image_small_webp',
                'reel__image_medium_webp',
                'reel__blurhash',
                'reel__duration',
                'reel__processing_status',
                'reel__processing_progress',
                'reel__processing_error',
            )
            .order_by('-vote_count')
        )

        # Bulk-fetch voted entries in one query instead of N+1
        voted_entry_ids = set()
        if user and entries:
            voted_entry_ids = set(
                CampaignVote.objects.filter(
                    user=user, entry_id__in=[e.id for e in entries]
                ).values_list('entry_id', flat=True)
            )

        entries_data = [
            {
                'id': entry.id,
                'user': {
                    'id': entry.user.id,
                    'username': entry.user.username,
                },
                # The main feed's media fields: renditions to choose from, and
                # never an unprocessed original (get_image_url resolved those).
                'reel': _entry_reel(entry.reel, request),
                'vote_count': entry.vote_count,
                'rank': entry.rank,
                'is_winner': entry.is_winner,
                'user_voted': entry.id in voted_entry_ids,
            }
            for entry in entries
        ]

        image_url = get_image_url(campaign.image, request)

        return Response(
            {
                'id': campaign.id,
                'title': campaign.title,
                'description': campaign.description,
                'campaign_type': campaign.campaign_type,
                'image': image_url,
                'prize_title': campaign.prize_title,
                'prize_description': campaign.prize_description,
                'prize_value': str(campaign.prize_value),
                'status': campaign.status,
                'start_date': campaign.start_date,
                'entry_deadline': campaign.entry_deadline,
                'voting_start': campaign.voting_start,
                'voting_end': campaign.voting_end,
                'total_entries': campaign.total_entries,
                'total_votes': campaign.total_votes,
                'winners_announced': campaign.winners_announced,
                'winner_count': campaign.winner_count,
                'min_followers': campaign.min_followers,
                'min_level': campaign.min_level,
                'min_votes_per_reel': campaign.min_votes_per_reel,
                'required_hashtags': campaign.required_hashtags,
                'current_user_id': user.id if user else None,
                'entries': entries_data,
            }
        )

    except Campaign.DoesNotExist:
        return Response({'error': 'Campaign not found'}, status=status.HTTP_404_NOT_FOUND)


# Helper functions
def update_campaign_rankings(campaign):
    """Update rankings for all entries in a campaign based on vote count"""
    entries = list(
        CampaignEntry.objects.filter(campaign=campaign, approved=True, disqualified=False)
        .only('id', 'rank')
        .order_by('-vote_count', '-created_at')
    )

    for rank, entry in enumerate(entries, start=1):
        entry.rank = rank
    CampaignEntry.objects.bulk_update(entries, ['rank'])


def notify_eligible_users(campaign):
    """Notify users who are eligible for the campaign"""
    # This would integrate with your notification system
    pass


def notify_voting_started(campaign):
    """Notify participants that voting has started"""
    entries = CampaignEntry.objects.filter(campaign=campaign)
    for entry in entries:
        CampaignNotification.objects.create(
            campaign=campaign,
            user=entry.user,
            notification_type='voting_started',
            message=f'Voting has started for {campaign.title}! Good luck!',
        )
