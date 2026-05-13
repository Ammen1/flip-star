"""
90-Day Contest System Views
API endpoints for tiered subscriptions, coin economy, scoring, and leaderboards
"""
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Count, Q, Sum, Avg, Max
from django.db import transaction
from datetime import timedelta, datetime
import json

from .models_contest import (
    UserSubscription, UserTier, CoinPackage, CoinTransaction, UserCoinBalance,
    PostBoost, GiftToCreator, ContestPostScore, ContestLeaderboard, ContestTimeline,
    AntiCheatLog, EligibilityVerification, GrandFinaleEntry, ExtraEntryPurchase
)
from .models import Reel, UserProfile


# ==================== USER TIER & SUBSCRIPTION ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_subscription(request):
    """Get current user's subscription details"""
    user = request.user
    
    # Get or create subscription
    subscription, created = UserSubscription.objects.get_or_create(
        user=user,
        defaults={
            'tier': UserTier.FREE,
            'expires_at': timezone.now() + timedelta(days=30),
        }
    )
    
    return Response({
        'tier': subscription.tier,
        'tier_name': subscription.get_tier_display(),
        'daily_post_limit': subscription.get_daily_post_limit(),
        'score_multiplier': subscription.get_score_multiplier(),
        'posts_today': subscription.posts_today,
        'can_post_today': subscription.can_post_today(),
        'expires_at': subscription.expires_at,
        'is_expired': subscription.is_expired(),
        'post_streak': subscription.post_streak,
        'longest_streak': subscription.longest_streak,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upgrade_subscription(request):
    """Upgrade user subscription tier"""
    user = request.user
    tier = request.data.get('tier')
    payment_method = request.data.get('payment_method', 'coins')
    
    if tier not in [t.value for t in UserTier]:
        return Response({'error': 'Invalid tier'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Define costs
    tier_costs = {
        'silver': 500,
        'gold': 1000,
        'vip': 5000,  # Annual
    }
    
    if tier == 'free':
        return Response({'error': 'Cannot upgrade to free tier'}, status=status.HTTP_400_BAD_REQUEST)
    
    cost = tier_costs.get(tier)
    
    # Check payment method
    if payment_method == 'coins':
        try:
            coin_balance = user.coin_balance
            coin_balance.spend_coins(cost, 'subscription_upgrade', description=f'Upgrade to {tier}')
        except UserCoinBalance.DoesNotExist:
            return Response({'error': 'No coin balance found'}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    # Update subscription
    subscription, _ = UserSubscription.objects.get_or_create(user=user)
    subscription.tier = tier
    subscription.payment_method = payment_method
    subscription.last_payment_date = timezone.now()
    
    if tier == 'vip':
        subscription.expires_at = timezone.now() + timedelta(days=365)
    else:
        subscription.expires_at = timezone.now() + timedelta(days=30)
    
    subscription.save()
    
    return Response({
        'message': f'Successfully upgraded to {tier}',
        'tier': tier,
        'expires_at': subscription.expires_at,
    })


# ==================== COIN ECONOMY ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_coin_packages(request):
    """Get available coin packages"""
    packages = CoinPackage.objects.filter(is_active=True)
    
    data = [{
        'id': p.id,
        'name': p.name,
        'price_etb': float(p.price_etb),
        'coin_amount': p.coin_amount,
        'bonus_coins': p.bonus_coins,
        'total_coins': p.get_total_coins(),
        'is_featured': p.is_featured,
    } for p in packages]
    
    return Response({'packages': data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_coin_balance(request):
    """Get user's coin balance and transaction history"""
    user = request.user
    
    # Get or create balance
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    
    # Get recent transactions
    transactions = CoinTransaction.objects.filter(user=user)[:20]
    
    return Response({
        'balance': balance.balance,
        'total_earned': balance.total_earned,
        'total_spent': balance.total_spent,
        'transactions': [{
            'id': t.id,
            'type': t.transaction_type,
            'coins': t.coins,
            'description': t.description,
            'created_at': t.created_at,
        } for t in transactions],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def purchase_coins(request):
    """Purchase coins with Telebirr or Airtime"""
    user = request.user
    package_id = request.data.get('package_id')
    payment_method = request.data.get('payment_method')  # 'telebirr' or 'airtime'
    phone_number = request.data.get('phone_number')
    
    try:
        package = CoinPackage.objects.get(id=package_id, is_active=True)
    except CoinPackage.DoesNotExist:
        return Response({'error': 'Package not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Calculate fee (5% for airtime)
    fee_percent = 0.05 if payment_method == 'airtime' else 0
    fee_amount = float(package.price_etb) * fee_percent
    final_price = float(package.price_etb) + fee_amount
    
    # In production, integrate with Telebirr API here
    # For now, simulate successful payment
    
    # Add coins to user balance
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    transaction = balance.add_coins(
        package.get_total_coins(),
        transaction_type='purchase',
        package=package,
        payment_method=payment_method,
        fee_amount=fee_amount,
        description=f'Purchased {package.name}'
    )
    
    return Response({
        'message': 'Coins purchased successfully',
        'coins_added': package.get_total_coins(),
        'new_balance': balance.balance,
        'payment_method': payment_method,
        'fee_charged': fee_amount if payment_method == 'airtime' else 0,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_gift(request):
    """Send gift to a user by username (simple gift endpoint)"""
    from .models import Notification, UserCoinBalance
    
    sender = request.user
    recipient_username = request.data.get('recipient_username')
    amount = request.data.get('amount')
    message = request.data.get('message', '')
    
    if not recipient_username:
        return Response({'error': 'recipient_username is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not amount or amount <= 0:
        return Response({'error': 'amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        recipient = User.objects.get(username=recipient_username)
    except User.DoesNotExist:
        return Response({'error': 'Recipient not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Deduct coins from sender
    try:
        sender_balance = sender.coin_balance
        sender_balance.spend_coins(
            amount,
            'gift',
            recipient=recipient,
            description=f'Gift to {recipient.username}'
        )
    except (UserCoinBalance.DoesNotExist, ValueError) as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    # Add coins to recipient
    recipient_balance, _ = UserCoinBalance.objects.get_or_create(user=recipient)
    recipient_balance.add_coins(amount, 'gift', sender=sender, description=f'Gift from {sender.username}')
    
    # Create gift record
    GiftToCreator.objects.create(
        sender=sender,
        recipient=recipient,
        coins=amount,
        bonus_points=5,
        message=message
    )
    
    # Update recipient's gift counters
    recipient_profile = recipient.profile
    recipient_profile.gifts_received_total += 1
    recipient_profile.gifts_received_today += 1
    recipient_profile.save()
    
    # Update sender's gift counters
    sender_profile = sender.profile
    sender_profile.gifts_sent_total += 1
    sender_profile.gifts_sent_today += 1
    sender_profile.save()
    
    # Create notification for recipient
    notification_message = f"{sender.username} sent you {amount} coins"
    if message:
        notification_message += f": {message}"
    
    Notification.objects.create(
        recipient=recipient,
        sender=sender,
        notification_type='gift',
        message=notification_message
    )
    
    return Response({
        'message': f'Gift of {amount} coins sent to {recipient_username}',
        'bonus_points_added': 5,
        'coins_deducted': amount,
        'coins_added_to_recipient': amount,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def gift_creator(request):
    """Gift coins to a creator (+5 bonus points to recipient)"""
    sender = request.user
    recipient_id = request.data.get('recipient_id')
    coins = request.data.get('coins', 100)
    reel_id = request.data.get('reel_id')
    
    try:
        recipient = User.objects.get(id=recipient_id)
    except User.DoesNotExist:
        return Response({'error': 'Recipient not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Deduct from sender
    try:
        sender_balance = sender.coin_balance
        sender_balance.spend_coins(
            coins, 
            'gift', 
            recipient=recipient,
            reel_id=reel_id,
            description=f'Gift to {recipient.username}'
        )
    except (UserCoinBalance.DoesNotExist, ValueError) as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    # Add to recipient
    recipient_balance, _ = UserCoinBalance.objects.get_or_create(user=recipient)
    recipient_balance.add_coins(coins, 'gift', sender=sender, description=f'Gift from {sender.username}')
    
    # Add bonus points to recipient's score
    # This would be implemented in the scoring system
    
    # Create gift record
    GiftToCreator.objects.create(
        sender=sender,
        recipient=recipient,
        reel_id=reel_id,
        coins=coins,
        bonus_points=5
    )
    
    return Response({
        'message': f'Gifted {coins} coins to {recipient.username}',
        'bonus_points_added': 5,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def boost_post(request):
    """Boost a post for 200 coins (2 hours featured)"""
    user = request.user
    reel_id = request.data.get('reel_id')
    
    try:
        reel = Reel.objects.get(id=reel_id, user=user)
    except Reel.DoesNotExist:
        return Response({'error': 'Post not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Check if already boosted
    if hasattr(reel, 'boost') and reel.boost.is_boost_active():
        return Response({'error': 'Post is already boosted'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Deduct coins
    cost = 200
    try:
        balance = user.coin_balance
        balance.spend_coins(cost, 'boost', reel=reel, description='Post boost')
    except (UserCoinBalance.DoesNotExist, ValueError) as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    # Create boost
    boost = PostBoost.objects.create(
        reel=reel,
        user=user,
        cost_coins=cost
    )
    
    # Mark reel as featured
    reel.is_featured = True
    reel.save(update_fields=['is_featured'])
    
    return Response({
        'message': 'Post boosted successfully',
        'boosted_until': boost.expires_at,
        'cost': cost,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def purchase_extra_entry(request):
    """Purchase extra post entry beyond daily limit (100 coins)"""
    user = request.user
    
    today = timezone.now().date()
    
    # Check if already purchased today
    if ExtraEntryPurchase.objects.filter(user=user, date=today).exists():
        return Response({'error': 'Already purchased extra entry today'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Deduct coins
    cost = 100
    try:
        balance = user.coin_balance
        balance.spend_coins(cost, 'extra_entry', description='Extra post entry')
    except (UserCoinBalance.DoesNotExist, ValueError) as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    # Record purchase
    ExtraEntryPurchase.objects.create(
        user=user,
        date=today,
        extra_entries_purchased=1,
        coins_spent=cost
    )
    
    return Response({
        'message': 'Extra entry purchased successfully',
        'extra_entries': 1,
        'cost': cost,
    })


# ==================== SCORING MATRIX ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_post_score(request, reel_id):
    """Get scoring details for a post"""
    user = request.user
    
    try:
        reel = Reel.objects.get(id=reel_id)
        score, _ = ContestPostScore.objects.get_or_create(
            reel=reel,
            user=reel.user,
            defaults={}
        )
    except Reel.DoesNotExist:
        return Response({'error': 'Post not found'}, status=status.HTTP_404_NOT_FOUND)
    
    return Response({
        'reel_id': reel_id,
        'total_score': score.total_score,
        'breakdown': {
            'creativity': {'score': score.creativity, 'max': 30, 'weight': 'admin'},
            'engagement': {'score': score.engagement, 'max': 25, 'weight': 'auto'},
            'consistency': {'score': score.consistency, 'max': 20, 'weight': 'auto'},
            'quality': {'score': score.quality, 'max': 15, 'weight': 'admin'},
            'theme': {'score': score.theme_relevance, 'max': 10, 'weight': 'admin'},
        },
        'is_judged': score.is_judged,
        'judged_at': score.judged_at,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def judge_post(request, reel_id):
    """Admin judging portal - assign scores to post"""
    user = request.user
    
    # Check if user is admin/judge
    if not user.is_staff:
        return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        reel = Reel.objects.get(id=reel_id)
    except Reel.DoesNotExist:
        return Response({'error': 'Post not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Get scores from request
    creativity = min(request.data.get('creativity', 0), 30)
    quality = min(request.data.get('quality', 0), 15)
    theme = min(request.data.get('theme_relevance', 0), 10)
    
    # Get or create score
    score, _ = ContestPostScore.objects.get_or_create(
        reel=reel,
        user=reel.user,
        defaults={}
    )
    
    # Update admin-assigned scores
    score.creativity = creativity
    score.quality = quality
    score.theme_relevance = theme
    score.is_judged = True
    score.judged_by = user
    score.judged_at = timezone.now()
    
    # Calculate engagement score
    likes = reel.likes.count() if hasattr(reel, 'likes') else 0
    shares = reel.shares if hasattr(reel, 'shares') else 0
    score.calculate_engagement(likes, shares)
    
    # Calculate consistency score
    try:
        streak = reel.user.contest_subscription.post_streak
    except:
        streak = 0
    score.calculate_consistency(streak)
    
    # Calculate total
    score.calculate_total()
    score.save()
    
    return Response({
        'message': 'Post judged successfully',
        'total_score': score.total_score,
        'breakdown': {
            'creativity': score.creativity,
            'engagement': score.engagement,
            'consistency': score.consistency,
            'quality': score.quality,
            'theme': score.theme_relevance,
        }
    })


# ==================== LEADERBOARDS ====================

@api_view(['GET'])
def get_leaderboard(request):
    """Get leaderboard for a specific period"""
    period = request.GET.get('period', 'daily')  # daily, weekly, monthly, grand
    date = request.GET.get('date')  # Optional specific date
    
    if not date:
        if period == 'daily':
            date = timezone.now().date()
        elif period == 'weekly':
            date = timezone.now().date() - timedelta(days=timezone.now().weekday())
        elif period == 'monthly':
            date = timezone.now().date().replace(day=1)
        else:
            date = timezone.now().date()
    
    try:
        leaderboard = ContestLeaderboard.objects.get(period=period, date=date)
        entries = leaderboard.entries
    except ContestLeaderboard.DoesNotExist:
        # Calculate on the fly
        entries = calculate_leaderboard(period, date)
    
    return Response({
        'period': period,
        'date': date,
        'entries': entries[:50],  # Top 50
    })


def calculate_leaderboard(period, date):
    """Calculate leaderboard entries for a period"""
    if period == 'daily':
        start = datetime.combine(date, datetime.min.time())
        end = start + timedelta(days=1)
        
        # Get top 10 + 5 random
        top_scores = ContestPostScore.objects.filter(
            created_at__date=date
        ).order_by('-total_score')[:10]
        
        # Get 5 random from remaining
        remaining = ContestPostScore.objects.filter(
            created_at__date=date
        ).exclude(id__in=[s.id for s in top_scores]).order_by('?')[:5]
        
        entries = []
        for i, score in enumerate(list(top_scores) + list(remaining), 1):
            entries.append({
                'rank': i,
                'user_id': score.user.id,
                'username': score.user.username,
                'score': score.total_score,
                'reel_id': score.reel.id,
            })
        
        return entries
    
    elif period == 'weekly':
        # Sum of scores over 7 days
        start = date
        end = start + timedelta(days=7)
        
        # Aggregate by user
        user_scores = ContestPostScore.objects.filter(
            created_at__date__gte=start,
            created_at__date__lt=end
        ).values('user').annotate(
            total=Sum('total_score'),
            post_count=Count('id')
        ).order_by('-total')[:5]
        
        entries = []
        for i, item in enumerate(user_scores, 1):
            user = User.objects.get(id=item['user'])
            entries.append({
                'rank': i,
                'user_id': user.id,
                'username': user.username,
                'score': item['total'],
                'posts': item['post_count'],
            })
        
        return entries
    
    return []


# ==================== ADMIN DASHBOARD ====================

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_contest_dashboard(request):
    """Admin contest dashboard with budget monitoring"""
    print(f"[CONTEST DASHBOARD] User: {request.user}, is_staff: {request.user.is_staff}")
    
    try:
        # Get active contest or create default
        try:
            contest = ContestTimeline.objects.get(is_active=True)
            print(f"[CONTEST DASHBOARD] Found active contest: {contest.name}")
        except ContestTimeline.DoesNotExist:
            print("[CONTEST DASHBOARD] No active contest, creating default...")
            # Create default contest
            contest = ContestTimeline.objects.create(
                name="90-Day Contest",
                start_date=timezone.now(),
                end_date=timezone.now() + timedelta(days=90),
                total_budget=2100000,
                flash_start_time=timezone.now().time().replace(hour=18, minute=0),
                flash_end_time=timezone.now().time().replace(hour=20, minute=0),
                is_active=True,
            )
            print(f"[CONTEST DASHBOARD] Created default contest: {contest.id}")
        
        # Budget breakdown
        total_budget = float(contest.total_budget)
        budget_breakdown = contest.get_budget_breakdown()
        
        # Stats with error handling
        try:
            total_participants = User.objects.filter(reel__isnull=False).distinct().count()
        except Exception as e:
            print(f"[CONTEST DASHBOARD] Error getting participants: {e}")
            total_participants = 0
            
        try:
            total_posts = Reel.objects.count()
        except Exception as e:
            print(f"[CONTEST DASHBOARD] Error getting posts: {e}")
            total_posts = 0
            
        try:
            coins_result = UserCoinBalance.objects.aggregate(Sum('total_earned'))
            total_coins = coins_result['total_earned__sum'] or 0
        except Exception as e:
            print(f"[CONTEST DASHBOARD] Error getting coins: {e}")
            total_coins = 0
        
        response_data = {
            'contest_name': contest.name,
            'days_remaining': contest.get_days_remaining(),
            'is_flash_hour': contest.is_flash_hour(),
            'flash_multiplier': contest.flash_multiplier if contest.is_flash_hour() else 1.0,
            'budget': {
                'total': total_budget,
                'allocated': {
                    'daily': total_budget * budget_breakdown['daily'] / 100,
                    'weekly': total_budget * budget_breakdown['weekly'] / 100,
                    'monthly': total_budget * budget_breakdown['monthly'] / 100,
                    'grand': total_budget * budget_breakdown['grand'] / 100,
                },
                'spent': {
                    'daily': float(contest.spent_daily),
                    'weekly': float(contest.spent_weekly),
                    'monthly': float(contest.spent_monthly),
                    'grand': float(contest.spent_grand),
                },
                'remaining': total_budget - (
                    float(contest.spent_daily) + float(contest.spent_weekly) +
                    float(contest.spent_monthly) + float(contest.spent_grand)
                ),
            },
            'stats': {
                'total_participants': total_participants,
                'total_posts': total_posts,
                'total_coins_distributed': total_coins,
            }
        }
        print(f"[CONTEST DASHBOARD] Success, returning data")
        return Response(response_data)
        
    except Exception as e:
        import traceback
        error_msg = f"[CONTEST DASHBOARD] ERROR: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def toggle_flash_challenge(request):
    """Toggle flash challenge (Happy Hour)"""
    try:
        contest = ContestTimeline.objects.get(is_active=True)
    except ContestTimeline.DoesNotExist:
        return Response({'error': 'No active contest'}, status=status.HTTP_404_NOT_FOUND)
    
    contest.is_flash_active = request.data.get('active', not contest.is_flash_active)
    contest.flash_start_time = request.data.get('start_time')
    contest.flash_end_time = request.data.get('end_time')
    contest.flash_multiplier = request.data.get('multiplier', 1.5)
    contest.save()
    
    return Response({
        'flash_active': contest.is_flash_active,
        'multiplier': contest.flash_multiplier,
        'start_time': contest.flash_start_time,
        'end_time': contest.flash_end_time,
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_judging_portal(request):
    """Get posts pending judgment"""
    status_filter = request.GET.get('status', 'pending')  # pending, judged, all
    
    if status_filter == 'pending':
        posts = ContestPostScore.objects.filter(is_judged=False).select_related('reel', 'user')[:50]
    elif status_filter == 'judged':
        posts = ContestPostScore.objects.filter(is_judged=True).select_related('reel', 'user')[:50]
    else:
        posts = ContestPostScore.objects.all().select_related('reel', 'user')[:50]
    
    return Response({
        'pending_count': ContestPostScore.objects.filter(is_judged=False).count(),
        'judged_count': ContestPostScore.objects.filter(is_judged=True).count(),
        'posts': [{
            'id': score.id,
            'reel_id': score.reel.id,
            'user': {
                'id': score.user.id,
                'username': score.user.username,
            },
            'caption': score.reel.caption if hasattr(score.reel, 'caption') else '',
            'image': score.reel.image.url if hasattr(score.reel, 'image') and score.reel.image else None,
            'current_scores': {
                'creativity': score.creativity,
                'quality': score.quality,
                'theme': score.theme_relevance,
            },
            'total_score': score.total_score,
            'is_judged': score.is_judged,
            'created_at': score.created_at,
        } for score in posts]
    })


# ==================== ANTI-CHEAT & ELIGIBILITY ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_phone(request):
    """Verify phone number (Ethio Telecom)"""
    user = request.user
    phone_number = request.data.get('phone_number')
    verification_code = request.data.get('verification_code')
    
    # Get or create eligibility record
    eligibility, _ = EligibilityVerification.objects.get_or_create(user=user)
    
    if not verification_code:
        # Generate and send code (integrate with SMS API)
        import random
        code = str(random.randint(100000, 999999))
        eligibility.phone_number = phone_number
        eligibility.verification_code = code
        eligibility.save()
        
        # In production: Send SMS via Ethio Telecom
        return Response({
            'message': 'Verification code sent',
            'phone_number': phone_number,
            # Remove in production:
            'debug_code': code,
        })
    
    # Verify code
    if eligibility.verification_code == verification_code:
        eligibility.is_phone_verified = True
        eligibility.save()
        
        # Check full eligibility
        is_eligible, message = eligibility.check_eligibility()
        
        return Response({
            'message': 'Phone verified successfully',
            'is_phone_verified': True,
            'is_fully_verified': is_eligible,
        })
    
    return Response({'error': 'Invalid verification code'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_age(request):
    """Verify age (18+) with ID upload"""
    user = request.user
    date_of_birth = request.data.get('date_of_birth')
    
    # Get or create eligibility record
    eligibility, _ = EligibilityVerification.objects.get_or_create(user=user)
    
    eligibility.date_of_birth = date_of_birth
    eligibility.save()
    
    # Check eligibility
    is_eligible, message = eligibility.check_eligibility()
    
    return Response({
        'date_of_birth': date_of_birth,
        'is_age_verified': is_eligible,
        'is_fully_verified': eligibility.is_fully_verified,
        'message': message,
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def anti_cheat_flags(request):
    """Get flagged accounts for review"""
    status_filter = request.GET.get('status', 'pending')
    
    flags = AntiCheatLog.objects.filter(status=status_filter)
    
    return Response({
        'count': flags.count(),
        'flags': [{
            'id': flag.id,
            'user': {
                'id': flag.user.id,
                'username': flag.user.username,
            },
            'flag_type': flag.flag_type,
            'description': flag.description,
            'evidence': flag.evidence,
            'status': flag.status,
            'created_at': flag.created_at,
        } for flag in flags]
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def review_flag(request, flag_id):
    """Review and resolve anti-cheat flag"""
    try:
        flag = AntiCheatLog.objects.get(id=flag_id)
    except AntiCheatLog.DoesNotExist:
        return Response({'error': 'Flag not found'}, status=status.HTTP_404_NOT_FOUND)
    
    flag.status = request.data.get('status', 'cleared')
    flag.reviewed_by = request.user
    flag.reviewed_at = timezone.now()
    flag.save()
    
    return Response({
        'message': f'Flag marked as {flag.status}',
        'flag_id': flag.id,
        'status': flag.status,
    })


# ==================== GRAND FINALE ====================

@api_view(['GET'])
def get_grand_finale(request):
    """Get Day 90 Grand Finale entries and standings"""
    try:
        contest = ContestTimeline.objects.get(is_active=True)
    except ContestTimeline.DoesNotExist:
        # Return empty grand finale data
        return Response({
            'days_remaining': 90,
            'is_grand_finale': False,
            'message': 'No active contest',
            'entries': [],
        })
    
    # Check if it's day 90
    days_remaining = contest.get_days_remaining()
    
    entries = GrandFinaleEntry.objects.filter(contest=contest).select_related('user', 'reel')
    
    return Response({
        'days_remaining': days_remaining,
        'is_grand_finale': days_remaining == 0,
        'entries': [{
            'rank': entry.rank,
            'user': {
                'id': entry.user.id,
                'username': entry.user.username,
            },
            'judge_score': entry.judge_total,
            'judge_weight': '70%',
            'public_votes': entry.public_votes,
            'public_weight': '30%',
            'final_score': float(entry.final_score),
            'is_winner': entry.is_winner,
            'prize': float(entry.prize_amount),
        } for entry in entries[:20]],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def vote_grand_finale(request):
    """Vote in Grand Finale with coins"""
    user = request.user
    entry_id = request.data.get('entry_id')
    coins = request.data.get('coins', 10)
    
    try:
        contest = ContestTimeline.objects.get(is_active=True)
        entry = GrandFinaleEntry.objects.get(id=entry_id, contest=contest)
    except (ContestTimeline.DoesNotExist, GrandFinaleEntry.DoesNotExist):
        return Response({'error': 'Entry not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Check if it's grand finale day
    if contest.get_days_remaining() != 0:
        return Response({'error': 'Grand finale voting is not open'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Deduct coins
    try:
        balance = user.coin_balance
        balance.spend_coins(coins, 'grand_vote', description=f'Vote for {entry.user.username}')
    except (UserCoinBalance.DoesNotExist, ValueError) as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    # Add vote
    entry.public_votes += 1
    entry.coins_received += coins
    entry.save()
    
    # Recalculate score
    entry.calculate_final_score()
    entry.save()
    
    return Response({
        'message': f'Voted for {entry.user.username}',
        'coins_spent': coins,
        'entry_votes': entry.public_votes,
    })


# ==================== CHECK ELIGIBILITY BEFORE UPLOAD ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_upload_eligibility(request):
    """Check if user can upload (18+, verified, within tier limits)"""
    user = request.user
    
    response = {
        'can_upload': True,
        'restrictions': [],
    }
    
    # Check age and phone verification
    try:
        eligibility = user.eligibility
        if not eligibility.is_fully_verified:
            is_eligible, message = eligibility.check_eligibility()
            if not is_eligible:
                response['can_upload'] = False
                response['restrictions'].append({
                    'type': 'verification',
                    'message': message,
                })
    except EligibilityVerification.DoesNotExist:
        response['can_upload'] = False
        response['restrictions'].append({
            'type': 'verification',
            'message': 'Age and phone verification required',
        })
    
    # Check subscription tier limits
    try:
        subscription = user.contest_subscription
        if not subscription.can_post_today():
            # Check if extra entry purchased
            today = timezone.now().date()
            extra_purchased = ExtraEntryPurchase.objects.filter(
                user=user, date=today
            ).exists()
            
            if extra_purchased:
                response['extra_entry_used'] = True
            else:
                response['can_upload'] = False
                response['restrictions'].append({
                    'type': 'tier_limit',
                    'message': f'Daily limit reached ({subscription.get_daily_post_limit()} posts/day)',
                    'upgrade_options': ['Purchase extra entry (100 coins)', 'Upgrade tier'],
                })
    except UserSubscription.DoesNotExist:
        pass
    
    # Check if flash hour (apply multiplier)
    try:
        contest = ContestTimeline.objects.get(is_active=True)
        if contest.is_flash_hour():
            response['flash_multiplier'] = contest.flash_multiplier
            response['flash_message'] = 'Flash Hour Active! Multiplier applied!'
    except ContestTimeline.DoesNotExist:
        pass
    
    return Response(response)
