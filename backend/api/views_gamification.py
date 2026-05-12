"""
Gamification API - Daily Spin, Coin Gifts, Login Bonuses, Streaks
"""
import random
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

# Spin reward tiers
SPIN_REWARDS = [
    {'type': 'coins_small', 'amount': 10, 'weight': 40, 'label': '10 Coins', 'emoji': '🪙'},
    {'type': 'coins_medium', 'amount': 25, 'weight': 30, 'label': '25 Coins', 'emoji': '🪙🪙'},
    {'type': 'coins_large', 'amount': 50, 'weight': 15, 'label': '50 Coins', 'emoji': '💰'},
    {'type': 'coins_jackpot', 'amount': 100, 'weight': 5, 'label': '100 Coins', 'emoji': '🏆'},
    {'type': 'xp_boost', 'amount': 50, 'weight': 8, 'label': '50 XP', 'emoji': '⚡'},
    {'type': 'streak_save', 'amount': 1, 'weight': 2, 'label': 'Streak Saver', 'emoji': '🛡️'},
]

DAILY_LOGIN_BONUS = {
    1: {'coins': 3, 'label': 'Day 1 Bonus'},
    2: {'coins': 10, 'label': 'Day 2 Bonus'},
    3: {'coins': 15, 'label': 'Day 3 Bonus'},
    4: {'coins': 20, 'label': 'Day 4 Bonus'},
    5: {'coins': 25, 'label': 'Day 5 Bonus'},
    6: {'coins': 30, 'label': 'Day 6 Bonus'},
    7: {'coins': 50, 'label': 'Week Streak! 🎉'},
}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gamification_status(request):
    """Get user's gamification status - coins, streaks, spin availability"""
    try:
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        if created:
            print(f"Created new UserProfile for user {request.user.username}")
    except Exception as e:
        print(f"Error creating UserProfile for {request.user.username}: {e}")
        return Response(
            {'error': 'Failed to create user profile'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    try:
        today = timezone.now().date()

        # Check if can spin today
        can_spin = profile.last_spin_date != today

        # Check login bonus for today
        login_bonus_available = profile.last_login_date != today

        # Calculate next login bonus
        streak_day = min(profile.login_streak + 1, 7)
        next_bonus = DAILY_LOGIN_BONUS.get(streak_day, DAILY_LOGIN_BONUS[7])

        # Reset daily counters if needed
        if profile.last_gift_reset != today:
            profile.gifts_sent_today = 0
            profile.gifts_received_today = 0
            profile.last_gift_reset = today
            profile.save()

        return Response({
            'coins': {
                'balance': profile.coins,
                'earned_total': profile.coins_earned_total,
                'spent_total': profile.coins_spent_total,
            },
            'spin': {
                'can_spin': can_spin,
                'last_spin_date': profile.last_spin_date,
                'spins_total': profile.spins_total,
                'rewards_preview': SPIN_REWARDS,
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
            'spin': {'can_spin': False, 'rewards_preview': SPIN_REWARDS},
            'login_streak': {'current': 0, 'longest': 0, 'bonus_available': False},
            'gifts': {'sent_today': 0, 'received_today': 0, 'sent_total': 0, 'received_total': 0},
            'points': {'balance': 0, 'earned_total': 0, 'withdrawn_total': 0}
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def daily_spin(request):
    """Perform daily spin wheel"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    today = timezone.now().date()
    
    # Check if already spun today
    if profile.last_spin_date == today:
        return Response({
            'error': 'Already spun today',
            'next_spin': 'tomorrow'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Improved weighted random selection with better randomness
    weights = [r['weight'] for r in SPIN_REWARDS]
    total_weight = sum(weights)
    
    # Use cryptographically secure random for better randomness
    random_num = random.SystemRandom().uniform(0, total_weight)
    
    # Shuffle rewards to avoid pattern bias
    shuffled_rewards = SPIN_REWARDS.copy()
    random.SystemRandom().shuffle(shuffled_rewards)
    
    cumulative = 0
    selected_reward = None
    for reward in shuffled_rewards:
        cumulative += reward['weight']
        if random_num <= cumulative:
            selected_reward = reward
            break
    
    if not selected_reward:
        selected_reward = SPIN_REWARDS[0]  # Default fallback
    
    # Process reward
    coins_earned = 0
    xp_earned = 0
    streak_saved = False
    
    with transaction.atomic():
        if selected_reward['type'] == 'coins_small':
            coins_earned = selected_reward['amount']
        elif selected_reward['type'] == 'coins_medium':
            coins_earned = selected_reward['amount']
        elif selected_reward['type'] == 'coins_large':
            coins_earned = selected_reward['amount']
        elif selected_reward['type'] == 'coins_jackpot':
            coins_earned = selected_reward['amount']
        elif selected_reward['type'] == 'xp_boost':
            xp_earned = selected_reward['amount']
            profile.xp += xp_earned
        elif selected_reward['type'] == 'streak_save':
            streak_saved = True
        
        # Update profile
        profile.coins += coins_earned
        profile.coins_earned_total += coins_earned
        profile.spins_total += 1
        profile.last_spin_date = today
        profile.save()
        
        # Log activity for campaign scoring
        GamificationActivity.objects.create(
            user=request.user,
            activity_type='spin_reward',
            points_value=coins_earned,
            activity_date=today,
            metadata={
                'spin_type': selected_reward['type'],
                'label': selected_reward['label'],
                'streak_saved': streak_saved
            }
        )
    
    return Response({
        'reward': selected_reward,
        'coins_earned': coins_earned,
        'xp_earned': xp_earned,
        'streak_saved': streak_saved,
        'new_balance': profile.coins,
        'spins_total': profile.spins_total,
        'can_spin_again': False,
        'next_spin': 'tomorrow'
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def claim_login_bonus(request):
    """Claim daily login bonus"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    today = timezone.now().date()
    now = timezone.now()
    
    # Check if already claimed today
    if profile.last_login_date == today:
        return Response({
            'error': 'Login bonus already claimed today',
            'next_claim': 'tomorrow'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Check streak continuity
    if profile.last_login_date:
        days_since_last = (today - profile.last_login_date).days
        if days_since_last > 1:
            # Streak broken
            profile.login_streak = 0
    
    # Increment streak (capped at 7)
    profile.login_streak = min(profile.login_streak + 1, 7)
    profile.last_login_date = today
    
    # Update longest streak
    if profile.login_streak > profile.longest_login_streak:
        profile.longest_login_streak = profile.login_streak
    
    # Get bonus for current streak day
    bonus = DAILY_LOGIN_BONUS.get(profile.login_streak, DAILY_LOGIN_BONUS[7])
    coins_earned = bonus['coins']
    
    with transaction.atomic():
        profile.coins += coins_earned
        profile.coins_earned_total += coins_earned
        profile.save()
        
        # Log activity
        GamificationActivity.objects.create(
            user=request.user,
            activity_type='login_bonus',
            points_value=coins_earned,
            activity_date=today,
            metadata={
                'streak_day': profile.login_streak,
                'label': bonus['label']
            }
        )
    
    return Response({
        'streak_day': profile.login_streak,
        'coins_earned': coins_earned,
        'label': bonus['label'],
        'new_balance': profile.coins,
        'login_streak': profile.login_streak,
        'longest_streak': profile.longest_login_streak,
        'next_bonus': DAILY_LOGIN_BONUS.get(min(profile.login_streak + 1, 7), DAILY_LOGIN_BONUS[7]) if profile.login_streak < 7 else DAILY_LOGIN_BONUS[7]
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
    
    today = timezone.now().date()
    
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
    
    # Check sender balance
    if sender_profile.coins < amount:
        return Response({
            'error': 'Insufficient coins',
            'balance': sender_profile.coins,
            'required': amount
        }, status=status.HTTP_400_BAD_REQUEST)
    
    with transaction.atomic():
        # Deduct from sender
        sender_profile.coins -= amount
        sender_profile.coins_spent_total += amount
        sender_profile.gifts_sent_today += 1
        sender_profile.gifts_sent_total += 1
        sender_profile.save()
        
        # Add to recipient
        recipient_profile.coins += amount
        recipient_profile.coins_earned_total += amount
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
        'new_balance': sender_profile.coins,
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
    today = timezone.now().date()
    
    # This is for the original streak field (posting streak)
    if profile.last_checkin:
        days_since = (today - profile.last_checkin.date()).days
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
