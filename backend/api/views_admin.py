from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.db.models import Count, Sum, Q, Avg
from django.utils import timezone
from datetime import timedelta
from .models import UserProfile, Reel, Quest, Competition, Subscription, Vote, Comment, Follow, SavedPost
from .serializers import UserSerializer, ReelSerializer, QuestSerializer, CompetitionSerializer

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_dashboard_stats(request):
    """Get dashboard statistics"""
    # User stats
    total_users = User.objects.count()
    active_users_today = User.objects.filter(last_login__gte=timezone.now() - timedelta(days=1)).count()
    active_users_week = User.objects.filter(last_login__gte=timezone.now() - timedelta(days=7)).count()
    active_users_month = User.objects.filter(last_login__gte=timezone.now() - timedelta(days=30)).count()
    new_users_today = User.objects.filter(date_joined__gte=timezone.now() - timedelta(days=1)).count()
    new_users_week = User.objects.filter(date_joined__gte=timezone.now() - timedelta(days=7)).count()
    
    # Content stats
    total_reels = Reel.objects.count()
    reels_today = Reel.objects.filter(created_at__gte=timezone.now() - timedelta(days=1)).count()
    reels_week = Reel.objects.filter(created_at__gte=timezone.now() - timedelta(days=7)).count()
    total_comments = Comment.objects.count()
    comments_today = Comment.objects.filter(created_at__gte=timezone.now() - timedelta(days=1)).count()
    
    # Engagement stats
    total_votes = Vote.objects.count()
    votes_today = Vote.objects.filter(created_at__gte=timezone.now() - timedelta(days=1)).count()
    total_follows = Follow.objects.count()
    follows_today = Follow.objects.filter(created_at__gte=timezone.now() - timedelta(days=1)).count()
    total_saves = SavedPost.objects.count()
    
    # Subscription stats
    subscription_stats = Subscription.objects.values('plan').annotate(count=Count('id'))
    
    # Top creators
    top_creators = User.objects.annotate(
        reel_count=Count('reels'),
        total_votes=Sum('reels__votes')
    ).order_by('-total_votes')[:10]
    
    top_creators_data = [{
        'id': user.id,
        'username': user.username,
        'reel_count': user.reel_count,
        'total_votes': user.total_votes or 0,
        'followers': user.followers.count()
    } for user in top_creators]
    
    # Trending reels
    trending_reels = Reel.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7)
    ).order_by('-votes')[:10]
    
    trending_reels_data = [{
        'id': reel.id,
        'caption': reel.caption[:50],
        'user': reel.user.username,
        'votes': reel.votes,
        'comments': reel.comments.count(),
        'created_at': reel.created_at
    } for reel in trending_reels]
    
    return Response({
        'users': {
            'total': total_users,
            'active_today': active_users_today,
            'active_week': active_users_week,
            'active_month': active_users_month,
            'new_today': new_users_today,
            'new_week': new_users_week
        },
        'content': {
            'total_reels': total_reels,
            'reels_today': reels_today,
            'reels_week': reels_week,
            'total_comments': total_comments,
            'comments_today': comments_today
        },
        'engagement': {
            'total_votes': total_votes,
            'votes_today': votes_today,
            'total_follows': total_follows,
            'follows_today': follows_today,
            'total_saves': total_saves
        },
        'subscriptions': list(subscription_stats),
        'top_creators': top_creators_data,
        'trending_reels': trending_reels_data
    })

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_users_list(request):
    """Get all users with detailed info"""
    users = User.objects.select_related('profile').annotate(
        reel_count=Count('reels'),
        follower_count=Count('followers'),
        following_count=Count('following')
    ).order_by('-date_joined')
    
    # Pagination
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    start = (page - 1) * page_size
    end = start + page_size
    
    # Search
    search = request.GET.get('search', '')
    if search:
        users = users.filter(
            Q(username__icontains=search) | 
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )
    
    total = users.count()
    users_page = users[start:end]
    
    data = [{
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'is_active': user.is_active,
        'is_staff': user.is_staff,
        'date_joined': user.date_joined,
        'last_login': user.last_login,
        'reel_count': user.reel_count,
        'follower_count': user.follower_count,
        'following_count': user.following_count,
        'level': user.profile.level if hasattr(user, 'profile') else 1,
        'xp': user.profile.xp if hasattr(user, 'profile') else 0,
        'subscription': Subscription.objects.filter(user=user).first().plan if Subscription.objects.filter(user=user).exists() else 'free'
    } for user in users_page]
    
    return Response({
        'users': data,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size
    })

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_user_detail(request, user_id):
    """Get detailed user information"""
    try:
        user = User.objects.select_related('profile').annotate(
            reel_count=Count('reels'),
            follower_count=Count('followers'),
            following_count=Count('following'),
            total_votes=Sum('reels__votes')
        ).get(id=user_id)
        
        recent_reels = Reel.objects.filter(user=user).order_by('-created_at')[:10]
        recent_comments = Comment.objects.filter(user=user).order_by('-created_at')[:10]
        
        subscription = Subscription.objects.filter(user=user).first()
        
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_active': user.is_active,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'date_joined': user.date_joined,
            'last_login': user.last_login,
            'reel_count': user.reel_count,
            'follower_count': user.follower_count,
            'following_count': user.following_count,
            'total_votes': user.total_votes or 0,
            'level': user.profile.level if hasattr(user, 'profile') else 1,
            'xp': user.profile.xp if hasattr(user, 'profile') else 0,
            'streak': user.profile.streak if hasattr(user, 'profile') else 0,
            'bio': user.profile.bio if hasattr(user, 'profile') else '',
            'subscription': {
                'plan': subscription.plan if subscription else 'free',
                'started_at': subscription.started_at if subscription else None,
                'expires_at': subscription.expires_at if subscription else None
            },
            'recent_reels': [{
                'id': reel.id,
                'caption': reel.caption,
                'votes': reel.votes,
                'created_at': reel.created_at
            } for reel in recent_reels],
            'recent_comments': [{
                'id': comment.id,
                'text': comment.text,
                'created_at': comment.created_at
            } for comment in recent_comments]
        })
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['PATCH'])
@permission_classes([IsAdminUser])
def admin_user_update(request, user_id):
    """Update user details"""
    try:
        user = User.objects.get(id=user_id)
        
        if 'is_active' in request.data:
            user.is_active = request.data['is_active']
        if 'is_staff' in request.data:
            user.is_staff = request.data['is_staff']
        if 'is_superuser' in request.data:
            user.is_superuser = request.data['is_superuser']
        if 'email' in request.data:
            user.email = request.data['email']
        if 'first_name' in request.data:
            user.first_name = request.data['first_name']
        if 'last_name' in request.data:
            user.last_name = request.data['last_name']
            
        user.save()
        
        # Update profile if provided
        if hasattr(user, 'profile'):
            if 'xp' in request.data:
                user.profile.xp = request.data['xp']
            if 'level' in request.data:
                user.profile.level = request.data['level']
            if 'bio' in request.data:
                user.profile.bio = request.data['bio']
            user.profile.save()
        
        return Response({'message': 'User updated successfully'})
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def admin_user_delete(request, user_id):
    """Delete a user"""
    try:
        user = User.objects.get(id=user_id)
        username = user.username
        user.delete()
        return Response({'message': f'User {username} deleted successfully'})
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_reels_list(request):
    """Get all reels with moderation info"""
    reels = Reel.objects.select_related('user').annotate(
        comment_count=Count('comments'),
        save_count=Count('saved_by')
    ).order_by('-created_at')
    
    # Pagination
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    start = (page - 1) * page_size
    end = start + page_size
    
    # Search
    search = request.GET.get('search', '')
    if search:
        reels = reels.filter(
            Q(caption__icontains=search) | 
            Q(user__username__icontains=search) |
            Q(hashtags__icontains=search)
        )
    
    total = reels.count()
    reels_page = reels[start:end]
    
    data = [{
        'id': reel.id,
        'user': {
            'id': reel.user.id,
            'username': reel.user.username
        },
        'caption': reel.caption,
        'hashtags': reel.hashtags,
        'votes': reel.votes,
        'comment_count': reel.comment_count,
        'save_count': reel.save_count,
        'image': reel.image.url if reel.image else None,
        'media': reel.media.url if reel.media else None,
        'created_at': reel.created_at
    } for reel in reels_page]
    
    return Response({
        'reels': data,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size
    })

@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def admin_reel_delete(request, reel_id):
    """Delete a reel"""
    try:
        reel = Reel.objects.get(id=reel_id)
        reel.delete()
        return Response({'message': 'Reel deleted successfully'})
    except Reel.DoesNotExist:
        return Response({'error': 'Reel not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_reel_boost(request, reel_id):
    """Boost reel votes"""
    try:
        reel = Reel.objects.get(id=reel_id)
        boost_amount = request.data.get('amount', 10)
        reel.votes += boost_amount
        reel.save()
        return Response({'message': f'Reel boosted by {boost_amount} votes', 'new_votes': reel.votes})
    except Reel.DoesNotExist:
        return Response({'error': 'Reel not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_subscription_upgrade(request, user_id):
    """Upgrade user subscription"""
    try:
        user = User.objects.get(id=user_id)
        plan = request.data.get('plan', 'pro')
        days = request.data.get('days', 30)
        
        subscription, created = Subscription.objects.get_or_create(user=user)
        subscription.plan = plan
        subscription.expires_at = timezone.now() + timedelta(days=days)
        subscription.save()
        
        return Response({
            'message': f'User upgraded to {plan} for {days} days',
            'subscription': {
                'plan': subscription.plan,
                'expires_at': subscription.expires_at
            }
        })
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_comments_list(request):
    """Get all comments for moderation"""
    comments = Comment.objects.select_related('user', 'reel').annotate(
        like_count=Count('comment_likes'),
        reply_count=Count('replies')
    ).order_by('-created_at')
    
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))
    start = (page - 1) * page_size
    end = start + page_size
    
    total = comments.count()
    comments_page = comments[start:end]
    
    data = [{
        'id': comment.id,
        'user': {
            'id': comment.user.id,
            'username': comment.user.username
        },
        'reel_id': comment.reel.id,
        'text': comment.text,
        'like_count': comment.like_count,
        'reply_count': comment.reply_count,
        'created_at': comment.created_at
    } for comment in comments_page]
    
    return Response({
        'comments': data,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size
    })

@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def admin_comment_delete(request, comment_id):
    """Delete a comment"""
    try:
        comment = Comment.objects.get(id=comment_id)
        comment.delete()
        return Response({'message': 'Comment deleted successfully'})
    except Comment.DoesNotExist:
        return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_analytics_export(request):
    """Export analytics data"""
    export_type = request.GET.get('type', 'users')
    
    if export_type == 'users':
        users = User.objects.all().values(
            'id', 'username', 'email', 'date_joined', 'last_login', 'is_active'
        )
        return Response(list(users))
    elif export_type == 'reels':
        reels = Reel.objects.all().values(
            'id', 'user__username', 'caption', 'votes', 'created_at'
        )
        return Response(list(reels))
    
    return Response({'error': 'Invalid export type'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def admin_wipe_all_posts(request):
    """Wipe all reels/posts and related data (comments, votes, saves, campaign entries)."""
    from .models import CommentLike, CommentReply
    from .models_campaign import CampaignEntry, CampaignVote, CampaignWinner, CampaignNotification
    
    results = {}
    results['campaign_votes'] = CampaignVote.objects.all().delete()[0]
    results['campaign_winners'] = CampaignWinner.objects.all().delete()[0]
    results['campaign_notifications'] = CampaignNotification.objects.all().delete()[0]
    results['campaign_entries'] = CampaignEntry.objects.all().delete()[0]
    results['comment_likes'] = CommentLike.objects.all().delete()[0]
    results['comment_replies'] = CommentReply.objects.all().delete()[0]
    results['comments'] = Comment.objects.all().delete()[0]
    results['saved_posts'] = SavedPost.objects.all().delete()[0]
    results['votes'] = Vote.objects.all().delete()[0]
    results['reels'] = Reel.objects.all().delete()[0]
    
    return Response({'message': 'All posts wiped!', 'deleted': results})
