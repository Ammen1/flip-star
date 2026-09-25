from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models import Reel
from api.models.boost import (
    BoostCampaign,
    BoostConfig,
    BoostEngagement,
    BoostImpression,
)
from api.models.contest import UserCoinBalance
from api.services import boost_tiers
from api.services.concurrency import claim_transition
from common.security import encrypted_endpoint


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_boost_config(request):
    """Get current boost configuration and pricing"""
    try:
        config = BoostConfig.objects.first()
        if not config:
            config = BoostConfig.objects.create()

        balance, _ = UserCoinBalance.objects.get_or_create(user=request.user)

        return Response(
            {
                # The three products, with what each costs, how long it runs
                # and where it places. The sheet shows these; the hourly
                # figures below still serve the older custom form.
                'tiers': boost_tiers.tier_list(),
                # So the sheet can mark a tier unaffordable rather than
                # letting somebody pick it and be refused.
                'coin_balance': balance.balance,
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
                    {
                        'hours': 6,
                        'label': '6 Hours',
                        'label_extra': '17% off',
                        'cost': float(config.calculate_cost(6, False)),
                    },
                    {
                        'hours': 12,
                        'label': '12 Hours',
                        'label_extra': '33% off',
                        'cost': float(config.calculate_cost(12, False)),
                    },
                    {
                        'hours': 24,
                        'label': '24 Hours',
                        'label_extra': '42% off',
                        'cost': float(config.calculate_cost(24, False)),
                    },
                    {
                        'hours': 72,
                        'label': '3 Days',
                        'label_extra': '56% off',
                        'cost': float(config.calculate_cost(72, False)),
                    },
                    {
                        'hours': 168,
                        'label': '7 Days',
                        'label_extra': '71% off',
                        'cost': float(config.calculate_cost(168, False)),
                    },
                ],
                'premium_targeting_surcharge': config.premium_targeting_surcharge,
                'platform_fee_percent': config.platform_fee_percent,
                'base_impression_rate': config.base_impression_rate,
                'user_limits': {
                    'max_daily_boosts': config.max_daily_boosts_per_user,
                    'max_active_per_post': config.max_active_boosts_per_post,
                },
            }
        )
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
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
            target_gender
            and target_gender != 'all'
            or target_age_min
            or target_age_max
            or target_location
        )

        cost = config.calculate_cost(duration_hours, has_premium_targeting)
        expected_impressions = config.get_expected_impressions(cost)

        return Response(
            {
                'cost': float(cost),
                'expected_impressions': expected_impressions,
                'has_premium_targeting': has_premium_targeting,
                'premium_surcharge_applied': has_premium_targeting,
            }
        )
    except Exception as e:
        return Response({'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def create_boost_campaign(request):
    """Create a new boost campaign"""
    try:
        user = request.user
        reel_id = request.data.get('reel_id')
        target_gender = request.data.get('target_gender', 'all')
        target_age_min = request.data.get('target_age_min')
        target_age_max = request.data.get('target_age_max')
        target_location = request.data.get('target_location', '')

        # One of the three named tiers, or the older hourly form. A tier
        # fixes cost, duration, placement and any guarantee; `duration_hours`
        # on its own keeps every existing client working unchanged.
        raw_type = request.data.get('boost_type')
        tier = None
        if raw_type:
            try:
                tier = boost_tiers.tier_for(raw_type)
            except ValueError as exc:
                return Response({'error': str(exc)}, status=400)
            duration_hours = tier.duration_hours
        else:
            raw_duration = request.data.get('duration_hours')
            if raw_duration is None:
                return Response({'error': 'boost_type or duration_hours is required'}, status=400)
            duration_hours = int(raw_duration)

        # Validate reel exists and belongs to user. The owner filter is what
        # stops anybody boosting somebody else's post -- a 404 rather than a
        # 403, so it does not confirm the post exists to a stranger.
        reel = get_object_or_404(Reel, id=reel_id, user=user)

        # Content taken down by moderation cannot be promoted. Without this
        # a post could be hidden from every feed and still be sold a boost,
        # taking coins for placement it can never receive.
        if getattr(reel, 'is_hidden', False):
            return Response(
                {
                    'error': 'This post is not eligible for boosting.',
                    'code': 'reel_not_boostable',
                },
                status=400,
            )

        # Get or create config
        config = BoostConfig.objects.first()
        if not config:
            config = BoostConfig.objects.create()

        # Check user limits
        today = timezone.now().date()
        boosts_today = BoostCampaign.objects.filter(user=user, created_at__date=today).count()

        if boosts_today >= config.max_daily_boosts_per_user:
            return Response(
                {
                    'error': f'Daily boost limit reached ({config.max_daily_boosts_per_user} per day)'
                },
                status=400,
            )

        # Check active boosts on this post
        active_boosts = BoostCampaign.objects.filter(
            reel=reel, status='active', end_time__gt=timezone.now()
        ).count()

        if active_boosts >= config.max_active_boosts_per_post:
            return Response(
                {
                    'error': f'Maximum active boosts for this post reached ({config.max_active_boosts_per_post})'
                },
                status=400,
            )

        # A tier boost is a product, and buying the same one twice for one
        # post is a double purchase rather than twice the reach: the feeds
        # read whether a post has *an* active boost, not how many. Refused
        # with its own code so the client can say "already boosted" instead
        # of a generic failure.
        #
        # This check is the friendly path, not the guarantee. Two requests
        # arriving together can both pass it; what stops them both creating a
        # campaign is the partial unique index on BoostCampaign, whose
        # IntegrityError is caught below and answered the same way.
        if (
            tier is not None
            and BoostCampaign.objects.filter(
                reel=reel, status='active', end_time__gt=timezone.now()
            ).exists()
        ):
            return Response(
                {
                    'error': 'This post already has an active boost.',
                    'code': 'already_boosted',
                },
                status=400,
            )

        # Check if premium targeting is used
        has_premium_targeting = bool(
            target_gender
            and target_gender != 'all'
            or target_age_min
            or target_age_max
            or target_location
        )

        # A tier's price is the price. The hourly model still prices the
        # older form, and a tier deliberately ignores the premium-targeting
        # surcharge: what was advertised is what is charged.
        if tier is not None:
            cost = Decimal(tier.coins)
            expected_impressions = (
                tier.guaranteed_impressions
                if tier.has_guarantee
                else config.get_expected_impressions(cost)
            )
        else:
            cost = config.calculate_cost(duration_hours, has_premium_targeting)
            expected_impressions = config.get_expected_impressions(cost)

        # Check user has enough coins. This is a soft pre-check for a fast,
        # friendly 400 -- the authoritative guard is the locked balance
        # read inside spend_coins() below, which is what actually prevents
        # two concurrent boost purchases from both passing this check
        # against the same stale balance and jointly overspending.
        profile = user.profile
        coin_balance, _ = UserCoinBalance.objects.get_or_create(user=user)
        cost_int = int(cost)
        if coin_balance.balance < cost_int:
            return Response(
                {
                    'error': 'Insufficient coins',
                    'required': cost_int,
                    'available': coin_balance.balance,
                },
                status=400,
            )

        # Calculate hourly budget for pacing
        hourly_budget = cost / duration_hours

        # Use transaction to ensure atomicity
        try:
            return _charge_and_create(
                user=user,
                reel=reel,
                tier=tier,
                config=config,
                cost=cost,
                cost_int=cost_int,
                coin_balance=coin_balance,
                profile=profile,
                duration_hours=duration_hours,
                expected_impressions=expected_impressions,
                hourly_budget=hourly_budget,
                target_gender=target_gender,
                target_age_min=target_age_min,
                target_age_max=target_age_max,
                target_location=target_location,
            )
        except IntegrityError:
            # Lost the race: another request created this post's boost
            # between the check above and the insert. The whole block rolled
            # back, so nothing was charged.
            return Response(
                {
                    'error': 'This post already has an active boost.',
                    'code': 'already_boosted',
                },
                status=400,
            )
    except Exception as e:
        return Response({'error': str(e)}, status=500)


def _charge_and_create(
    *,
    user,
    reel,
    tier,
    config,
    cost,
    cost_int,
    coin_balance,
    profile,
    duration_hours,
    expected_impressions,
    hourly_budget,
    target_gender,
    target_age_min,
    target_age_max,
    target_location,
):
    """Take the coins and record the campaign, together or not at all.

    Split out so the IntegrityError from the one-active-boost constraint can
    be caught around the whole transaction: caught inside it, the rollback
    would already have happened and the coins would still read as spent.
    """
    with transaction.atomic():
        # Route the spend through the wallet ledger (UserCoinBalance +
        # a CoinTransaction row) instead of decrementing profile.coins
        # directly -- previously this only touched profile.coins, so
        # the purchase never appeared in wallet/transactions/ and
        # UserCoinBalance.balance (what wallet_summary actually shows)
        # silently drifted out of sync with it.
        try:
            coin_balance.spend_coins(
                cost_int,
                transaction_type='boost_campaign',
                description=f'Boost campaign for reel #{reel.id}',
            )
        except ValueError:
            return Response(
                {
                    'error': 'Insufficient coins',
                    'required': cost_int,
                    'available': coin_balance.balance,
                },
                status=400,
            )
        profile.coins = coin_balance.balance
        profile.coins_spent_total += cost_int
        profile.save(update_fields=['coins', 'coins_spent_total'])

        # Create campaign
        campaign = BoostCampaign.objects.create(
            user=user,
            reel=reel,
            boost_type=tier.key if tier else 'custom',
            placement=tier.placement if tier else boost_tiers.TRENDING,
            guaranteed_impressions=tier.guaranteed_impressions if tier else None,
            duration_hours=duration_hours,
            coins_spent=cost,
            coins_remaining=cost,
            end_time=timezone.now() + timedelta(hours=duration_hours),
            expected_impressions=expected_impressions,
            hourly_budget=hourly_budget,
            target_gender=target_gender if target_gender != 'all' else None,
            target_age_min=int(target_age_min) if target_age_min else None,
            target_age_max=int(target_age_max) if target_age_max else None,
            # target_location has no null=True (a CharField, by Django's
            # own convention -- 'no value' is '', not None); unlike
            # target_gender/target_age_*, which do allow null, passing
            # None here violates the NOT NULL constraint and 500s every
            # boost campaign with no location filter. Present in master
            # too -- this was never exercised until this codebase's real
            # DB-backed tests actually ran (see tests/conftest.py's
            # MIGRATIONS_ARE_REPLAYABLE history).
            target_location=target_location or '',
        )

        # Update reel
        reel.is_boosted = True
        reel.active_boost_campaign = campaign
        reel.save()

    return Response(
        {
            'success': True,
            'campaign_id': campaign.id,
            'boost_type': campaign.boost_type,
            'placement': campaign.placement,
            'guaranteed_impressions': campaign.guaranteed_impressions,
            'cost': float(cost),
            'expected_impressions': expected_impressions,
            'end_time': campaign.end_time.isoformat(),
            'remaining_coins': profile.coins,
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_user_boost_campaigns(request):
    """Get all boost campaigns for the current user"""
    try:
        user = request.user
        campaigns = BoostCampaign.objects.filter(user=user).order_by('-created_at')

        campaigns_data = []
        for campaign in campaigns:
            campaigns_data.append(
                {
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
                    }
                    if campaign.target_gender or campaign.target_age_min or campaign.target_location
                    else None,
                }
            )

        return Response({'campaigns': campaigns_data})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_boost_campaign_detail(request, campaign_id):
    """Get detailed information about a specific boost campaign"""
    try:
        user = request.user
        campaign = get_object_or_404(BoostCampaign, id=campaign_id, user=user)

        # Get engagement breakdown
        engagements = (
            campaign.engagements.values('engagement_type')
            .annotate(count=Count('id'))
            .order_by('engagement_type')
        )

        engagement_breakdown = {e['engagement_type']: e['count'] for e in engagements}

        # Get daily stats
        daily_stats = campaign.daily_stats.order_by('-date')[:7]

        return Response(
            {
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
                }
                if campaign.target_gender or campaign.target_age_min or campaign.target_location
                else None,
            }
        )
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
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
        cancellation_fee = refund_amount * (
            Decimal(config.cancellation_fee_percent) / Decimal('100')
        )
        final_refund = refund_amount - cancellation_fee

        with transaction.atomic():
            # Claim the cancellation before paying anything out.
            #
            # The status check above reads a value fetched before this request
            # did any work, and two taps on Cancel both passed it. Neither held
            # a lock, so both went on to refund: the user was paid twice for
            # one campaign, and the second refund_amount overwrote the first in
            # the record, hiding the duplicate.
            #
            # A single conditional UPDATE settles it. Exactly one caller finds
            # the campaign still active; the other gets zero rows and returns
            # without touching the wallet. Everything that must move with the
            # status moves in the same statement, so a crash cannot leave a
            # cancelled campaign still holding coins.
            claimed = claim_transition(
                BoostCampaign,
                campaign.id,
                expect='active',
                to='cancelled',
                cancelled_at=timezone.now(),
                coins_remaining=Decimal('0'),
                refund_amount=final_refund,
                refunded_at=timezone.now(),
            )
            if not claimed:
                campaign.refresh_from_db()
                return Response(
                    {'error': f'Campaign is {campaign.status}, cannot cancel'}, status=400
                )

            # Refunded through the locking helper. `profile.coins += n` read and
            # wrote in separate statements, so one of two concurrent credits
            # was lost -- and a bare save() rewrote every column of the profile
            # from a pre-race snapshot.
            if final_refund > 0:
                user.profile.add_coins(int(final_refund), total_field=None)

            # Update reel if this was the active campaign
            if campaign.reel.active_boost_campaign_id == campaign.id:
                Reel.objects.filter(pk=campaign.reel_id).update(
                    is_boosted=False, active_boost_campaign=None
                )

        campaign.refresh_from_db()

        return Response(
            {
                'success': True,
                'refund_amount': float(final_refund),
                'cancellation_fee': float(cancellation_fee),
                'remaining_coins': user.profile.coins,
            }
        )
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
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
@encrypted_endpoint
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
@encrypted_endpoint
def get_eligible_boosts(request):
    """Get boosted posts eligible for the current user's feed"""
    try:
        user = request.user
        profile = user.profile

        # Get active campaigns with remaining budget
        now = timezone.now()
        eligible_campaigns = (
            BoostCampaign.objects.filter(status='active', end_time__gt=now, coins_remaining__gt=0)
            .select_related('reel', 'reel__user')
            .prefetch_related('impressions')
        )

        # Filter by targeting and frequency capping
        filtered_campaigns = []
        for campaign in eligible_campaigns:
            # Skip if user is the post owner
            if campaign.reel.user == user:
                continue

            # Check if user already follows (boosts are for non-followers)
            from api.models import Follow

            is_follower = Follow.objects.filter(
                follower=user, following=campaign.reel.user
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
                    viewed_at__gte=now - timedelta(hours=config.frequency_cap_hours),
                ).exists()
                if last_view:
                    continue

            filtered_campaigns.append(campaign)

        # Return reel IDs for feed injection
        reel_ids = [campaign.reel.id for campaign in filtered_campaigns]

        return Response(
            {
                'eligible_reel_ids': reel_ids,
                'count': len(reel_ids),
            }
        )
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def record_boost_impression(request):
    """Record that a user viewed a boosted post"""
    try:
        user = request.user
        reel_id = request.data.get('reel_id')

        # Find active campaign for this reel
        campaign = BoostCampaign.objects.filter(
            reel_id=reel_id, status='active', end_time__gt=timezone.now(), coins_remaining__gt=0
        ).first()

        if not campaign:
            return Response({'success': False, 'message': 'No active campaign'})

        # Check frequency cap
        config = BoostConfig.objects.first()
        if config:
            last_view = BoostImpression.objects.filter(
                campaign=campaign,
                viewer=user,
                viewed_at__gte=timezone.now() - timedelta(hours=config.frequency_cap_hours),
            ).exists()
            if last_view:
                return Response({'success': False, 'message': 'Frequency cap reached'})

        # Record impression
        impression, created = BoostImpression.objects.get_or_create(campaign=campaign, viewer=user)

        if created:
            # Update campaign stats
            campaign.impressions_served += 1

            # Deduct coins based on pacing
            coins_to_deduct = (
                campaign.hourly_budget / config.base_impression_rate if config else Decimal('1')
            )
            if campaign.coins_remaining >= coins_to_deduct:
                campaign.coins_remaining -= coins_to_deduct
            else:
                campaign.coins_remaining = Decimal('0')
                campaign.status = 'exhausted'

            # A guaranteed campaign is finished when its guarantee is met,
            # not when its budget runs out -- Viral sells 5,000 impressions,
            # and stopping short of them while the window is still open
            # would be selling a number the platform did not deliver.
            # Counted from BoostImpression rows, which is what makes the
            # guarantee real rather than a figure printed on a product.
            if (
                campaign.guaranteed_impressions
                and campaign.impressions_served >= campaign.guaranteed_impressions
            ):
                campaign.status = 'completed'
                campaign.coins_remaining = Decimal('0')

            campaign.save()

            # Update reel stats
            campaign.reel.total_boost_impressions += 1
            campaign.reel.save()

        return Response({'success': True})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def record_boost_engagement(request):
    """Record engagement on a boosted post"""
    try:
        user = request.user
        reel_id = request.data.get('reel_id')
        engagement_type = request.data.get('engagement_type')  # 'like', 'comment', 'share'

        # Find active campaign for this reel
        campaign = BoostCampaign.objects.filter(
            reel_id=reel_id, status='active', end_time__gt=timezone.now()
        ).first()

        if not campaign:
            return Response({'success': False, 'message': 'No active campaign'})

        # Record engagement
        engagement, created = BoostEngagement.objects.get_or_create(
            campaign=campaign, user=user, engagement_type=engagement_type
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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def check_pacing_engine(request):
    """Pacing engine task - ensures budget is distributed evenly over duration"""
    try:
        config = BoostConfig.objects.first()
        if not config:
            config = BoostConfig.objects.create()

        now = timezone.now()

        # Get all active campaigns
        active_campaigns = BoostCampaign.objects.filter(
            status='active', end_time__gt=now, coins_remaining__gt=0
        )

        paused_count = 0
        for campaign in active_campaigns:
            hours_elapsed = (now - campaign.start_time).total_seconds() / 3600
            expected_spend = campaign.hourly_budget * hours_elapsed

            # Calculate actual spend
            actual_spend = campaign.coins_spent - campaign.coins_remaining

            # If we spent more than expected + tolerance, pause the campaign
            if actual_spend > expected_spend * config.pacing_tolerance:
                campaign.status = 'paused'
                campaign.save()

                # Update reel
                if campaign.reel.active_boost_campaign == campaign:
                    campaign.reel.is_boosted = False
                    campaign.reel.active_boost_campaign = None
                    campaign.reel.save()

                paused_count += 1

        return Response(
            {
                'success': True,
                'campaigns_checked': active_campaigns.count(),
                'campaigns_paused': paused_count,
            }
        )
    except Exception as e:
        return Response({'error': str(e)}, status=500)
