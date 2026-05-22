"""
Gamification API - Daily Login Streak and Coin Gifts
"""
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User

from .models import UserProfile
from .models_campaign_extended import GamificationActivity
from .models_contest import UserCoinBalance


@api_view(['GET'])
def debug_gamification(request):
    """Debug endpoint to check if gamification system is working"""
    try:
        # Check if UserProfile model exists and has gamification fields
        user_count = User.objects.count()
        profile_count = UserProfile.objects.count()
        
        # Test creating a profile
        test_user = User.objects.first()
        if test_user:
            profile, created = UserProfile.objects.get_or_create(user=test_user)
            
            return Response({
                'status': 'success',
                'debug_info': {
                    'total_users': user_count,
                    'total_profiles': profile_count,
                    'test_user': test_user.username,
                    'profile_created': created,
                    'profile_fields': {
                        'coins': profile.coins,
                        'login_streak': profile.login_streak,
                        'last_spin_date': profile.last_spin_date,
                        'spins_total': profile.spins_total,
                    },
                    'has_gamification_fields': True
                }
            })
        else:
            return Response({
                'status': 'error',
                'message': 'No users found in database'
            })
            
    except Exception as e:
        return Response({
            'status': 'error',
            'error': str(e),
            'message': 'Gamification system not working'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

DAILY_LOGIN_BONUS = {
    'daily': {'coins': 3, 'label': 'Daily Bonus'},
    7: {'coins': 50, 'label': '7 Day Streak Bonus! 🎉'},
    30: {'coins': 150, 'label': '30 Day Streak Bonus! 🎉'},
}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gamification_status(request):
    """Get user's gamification status - coins, streaks"""
    try:
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        if created:
            print(f"Created new UserProfile for user {request.user.username}")
        
        coin_balance, _ = UserCoinBalance.objects.get_or_create(user=request.user)
    except Exception as e:
        print(f"Error creating UserProfile for {request.user.username}: {e}")
        return Response(
            {'error': 'Failed to create user profile'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    try:
        today = timezone.localdate()

        # Check login bonus for today
        login_bonus_available = profile.last_login_date != today

        # Calculate next login bonus (3 coins daily, with milestone bonuses at 7 and 30 days)
        next_streak = profile.login_streak + 1
        next_bonus = DAILY_LOGIN_BONUS.get('daily')
        if next_streak == 7:
            next_bonus = DAILY_LOGIN_BONUS.get(7)
        elif next_streak == 30:
            next_bonus = DAILY_LOGIN_BONUS.get(30)

        # Reset daily counters if needed
        if profile.last_gift_reset != today:
            profile.gifts_sent_today = 0
            profile.gifts_received_today = 0
            profile.last_gift_reset = today
            profile.save()

        return Response({
            'coins': {
                'balance': coin_balance.balance,
                'earned_total': coin_balance.total_earned,
                'spent_total': coin_balance.total_spent,
            },
            'login_streak': {
                'current': profile.login_streak,
                'longest': profile.longest_login_streak,
            'last_login': profile.last_login_date,
            'bonus_available': login_bonus_available,
            'next_bonus': next_bonus,
        },
        'gifts': {
            'sent_today': profile.gifts_sent_today,
            'received_today': profile.gifts_received_today,
            'sent_total': profile.gifts_sent_total,
            'received_total': profile.gifts_received_total,
        },
        'points': {
            'balance': profile.points,
            'earned_total': profile.points_earned_total,
            'withdrawn_total': profile.points_withdrawn_total,
        }
    })
    except Exception as e:
        print(f'[gamification_status] Error: {e}')
        return Response({
            'coins': {'balance': 0, 'earned_total': 0, 'spent_total': 0},
            'login_streak': {'current': 0, 'longest': 0, 'bonus_available': False},
            'gifts': {'sent_today': 0, 'received_today': 0, 'sent_total': 0, 'received_total': 0},
            'points': {'balance': 0, 'earned_total': 0, 'withdrawn_total': 0}
        })



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def claim_login_bonus(request):
    """Claim daily login bonus"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    coin_balance, _ = UserCoinBalance.objects.get_or_create(user=request.user)
    today = timezone.localdate()
    now = timezone.now()

    print(f"[STREAK DEBUG] User: {request.user.username}, Today: {today}, Last login: {profile.last_login_date}, Current streak: {profile.login_streak}")

    # Check if already claimed today
    if profile.last_login_date == today:
        print(f"[STREAK DEBUG] Already claimed today")
        return Response({
            'error': 'Login bonus already claimed today',
            'next_claim': 'tomorrow'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Check streak continuity (use local calendar days)
    if profile.last_login_date:
        days_since_last = (today - profile.last_login_date).days
        print(f"[STREAK DEBUG] Days since last login: {days_since_last}")
        if days_since_last > 1:
            # Streak broken — reset to 0 before increment
            print(f"[STREAK DEBUG] Streak broken, resetting to 0")
            profile.login_streak = 0
        elif days_since_last == 1:
            # Consecutive day - keep current streak, will increment below
            print(f"[STREAK DEBUG] Consecutive day, keeping streak at {profile.login_streak}")
        # days_since_last == 0 means already claimed (handled above)
    else:
        # First-ever claim — start at 0, will increment to 1
        print(f"[STREAK DEBUG] First ever claim, setting streak to 0")
        profile.login_streak = 0

    # Increment streak (capped at 30)
    profile.login_streak = min(profile.login_streak + 1, 30)
    profile.last_login_date = today
    print(f"[STREAK DEBUG] New streak: {profile.login_streak}")
    
    # Update longest streak
    if profile.login_streak > profile.longest_login_streak:
        profile.longest_login_streak = profile.login_streak
    
    # Calculate bonus: 3 coins daily, with milestone bonuses at 7 and 30 days
    coins_earned = DAILY_LOGIN_BONUS['daily']['coins']  # Base daily bonus
    label = DAILY_LOGIN_BONUS['daily']['label']
    
    # Add milestone bonuses (REPLACE daily bonus, not add to it)
    if profile.login_streak == 7:
        coins_earned = DAILY_LOGIN_BONUS[7]['coins']
        label = DAILY_LOGIN_BONUS[7]['label']
        print(f"[STREAK DEBUG] 7 day milestone! Earning {coins_earned} coins")
    elif profile.login_streak == 30:
        coins_earned = DAILY_LOGIN_BONUS[30]['coins']
        label = DAILY_LOGIN_BONUS[30]['label']
        print(f"[STREAK DEBUG] 30 day milestone! Earning {coins_earned} coins")
    
    with transaction.atomic():
        # Update coin balance using UserCoinBalance
        coin_balance.add_earned(coins_earned, transaction_type='daily_login', description=f'Login bonus: {label}')
        
        # Update profile
        profile.save()
        
        # Log activity
        GamificationActivity.objects.create(
            user=request.user,
            activity_type='login_bonus',
            points_value=coins_earned,
            activity_date=today,
            metadata={
                'streak_day': profile.login_streak,
                'label': label
            }
        )
    
    print(f"[STREAK DEBUG] Bonus claimed: {coins_earned} coins, New balance: {coin_balance.balance}")
    
    return Response({
        'streak_day': profile.login_streak,
        'coins_earned': coins_earned,
        'label': label,
        'new_balance': coin_balance.balance,
        'login_streak': profile.login_streak,
        'longest_streak': profile.longest_login_streak,
        'next_bonus': DAILY_LOGIN_BONUS.get('daily')
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_coin_gift(request):
    """Send coin gift to another user"""
    recipient_id = request.data.get('recipient_id')
    recipient_username = request.data.get('recipient_username') or request.data.get('recipient_id')
    amount = request.data.get('amount', 10)
    message = request.data.get('message', '')
    
    if not recipient_username:
        return Response({'error': 'Recipient username required'}, status=status.HTTP_400_BAD_REQUEST)
    
    if amount < 1 or amount > 100:
        return Response({'error': 'Gift amount must be between 1-100 coins'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Try to find user by username first (remove @ if present)
        clean_username = recipient_username.lstrip('@')
        recipient = User.objects.get(username__iexact=clean_username)
    except User.DoesNotExist:
        return Response({'error': f'User "{recipient_username}" not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if recipient == request.user:
        return Response({'error': 'Cannot gift yourself'}, status=status.HTTP_400_BAD_REQUEST)
    
    sender_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    recipient_profile, _ = UserProfile.objects.get_or_create(user=recipient)
    sender_coin_balance, _ = UserCoinBalance.objects.get_or_create(user=request.user)
    recipient_coin_balance, _ = UserCoinBalance.objects.get_or_create(user=recipient)
    
    today = timezone.localdate()
    
    # Reset daily counters if needed
    if sender_profile.last_gift_reset != today:
        sender_profile.gifts_sent_today = 0
        sender_profile.last_gift_reset = today
    
    # Check daily limit (10 gifts per day)
    if sender_profile.gifts_sent_today >= 10:
        return Response({
            'error': 'Daily gift limit reached (10 per day)',
            'limit': 10,
            'sent_today': sender_profile.gifts_sent_today
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check sender balance using UserCoinBalance
    if sender_coin_balance.balance < amount:
        return Response({
            'error': 'Insufficient coins',
            'balance': sender_coin_balance.balance,
            'required': amount
        }, status=status.HTTP_400_BAD_REQUEST)
    
    with transaction.atomic():
        # Deduct from sender using UserCoinBalance (restrict to purchased coins for gifting)
        try:
            sender_coin_balance.spend_coins(amount, transaction_type='gift_sent', restrict_earned=True, description=f'Gift to {recipient.username}')
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        # Add to recipient using UserCoinBalance
        recipient_coin_balance.add_earned(amount, transaction_type='gift_received', description=f'Gift from {request.user.username}')
        
        # Update profile counters
        sender_profile.gifts_sent_today += 1
        sender_profile.gifts_sent_total += 1
        sender_profile.save()
        
        recipient_profile.gifts_received_today += 1
        recipient_profile.gifts_received_total += 1
        recipient_profile.save()
        
        # Log for sender (expense)
        GamificationActivity.objects.create(
            user=request.user,
            activity_type='coin_gift_sent',
            points_value=-amount,  # Negative for sending
            activity_date=today,
            metadata={
                'recipient_id': recipient.id,
                'recipient_username': recipient.username,
                'message': message
            }
        )
        
        # Log for recipient (earned)
        GamificationActivity.objects.create(
            user=recipient,
            activity_type='coin_gift_received',
            points_value=amount,
            activity_date=today,
            metadata={
                'sender_id': request.user.id,
                'sender_username': request.user.username,
                'message': message
            }
        )
    
    return Response({
        'success': True,
        'amount': amount,
        'recipient': {
            'id': recipient.id,
            'username': recipient.username
        },
        'new_balance': sender_coin_balance.balance,
        'gifts_sent_today': sender_profile.gifts_sent_today,
        'gifts_remaining_today': 10 - sender_profile.gifts_sent_today
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gift_history(request):
    """Get coin gift history for current user"""
    received = GamificationActivity.objects.filter(
        user=request.user,
        activity_type='coin_gift_received'
    ).order_by('-created_at')[:20]
    
    sent = GamificationActivity.objects.filter(
        user=request.user,
        activity_type='coin_gift_sent'
    ).order_by('-created_at')[:20]
    
    return Response({
        'received': [{
            'id': g.id,
            'amount': float(g.points_value),
            'sender': g.metadata.get('sender_username', 'Unknown'),
            'message': g.metadata.get('message', ''),
            'date': g.created_at
        } for g in received],
        'sent': [{
            'id': g.id,
            'amount': abs(float(g.points_value)),
            'recipient': g.metadata.get('recipient_username', 'Unknown'),
            'message': g.metadata.get('message', ''),
            'date': g.created_at
        } for g in sent]
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recent_activity(request):
    """Get recent gamification activity for the user"""
    activities = GamificationActivity.objects.filter(
        user=request.user
    ).order_by('-created_at')[:30]
    
    return Response({
        'activities': [{
            'id': a.id,
            'type': a.activity_type,
            'points': float(a.points_value),
            'date': a.created_at,
            'metadata': a.metadata
        } for a in activities]
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_in(request):
    """Check in for daily streak (separate from login bonus)"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    today = timezone.localdate()

    # This is for the original streak field (posting streak)
    if profile.last_checkin:
        last_checkin_date = timezone.localtime(profile.last_checkin).date()
        if last_checkin_date == today:
            # Already checked in today — return current streak without changes
            return Response({
                'streak': profile.streak,
                'xp_reward': 0,
                'message': f'Already checked in today. Streak: {profile.streak}'
            })
        days_since = (today - last_checkin_date).days
        if days_since > 1:
            profile.streak = 0
    
    profile.streak += 1
    profile.last_checkin = timezone.now()
    profile.save()
    
    # Small XP reward for checkin
    xp_reward = min(profile.streak * 5, 50)  # Cap at 50 XP
    profile.xp += xp_reward
    profile.save()
    
    return Response({
        'streak': profile.streak,
        'xp_reward': xp_reward,
        'message': f'{profile.streak} day streak! +{xp_reward} XP'
    })
