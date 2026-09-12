from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.db.models import Count, Sum, Q, Avg
from django.utils import timezone
from datetime import timedelta
from api.models import UserProfile, Reel, Quest, Competition, Subscription, Vote, Comment, Follow, SavedPost
from api.serializers.core import UserSerializer, ReelSerializer, QuestSerializer, CompetitionSerializer, reel_media_payload
from api.views.subscription import mask_phone_number
from common.permissions import HasAdminPermission

@api_view(['GET'])
@permission_classes([HasAdminPermission])
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
@permission_classes([HasAdminPermission])
def admin_users_list(request):
    """Get all users with detailed info"""
    # Use simple Count annotations without distinct - these should be accurate
    users = User.objects.select_related('profile').annotate(
        reel_count=Count('reels'),
        follower_count=Count('followers'),
        following_count=Count('following')
    ).order_by('-date_joined')
    
    # Debug: print first user counts
    if users.exists():
        first_user = users.first()
        print(f'[ADMIN] First user: {first_user.username}, reels: {first_user.reel_count}, followers: {first_user.follower_count}, following: {first_user.following_count}')
        print(f'[ADMIN] Direct count - reels: {first_user.reels.count()}, followers: {first_user.followers.count()}, following: {first_user.following.count()}')
    
    # Pagination
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    start = (page - 1) * page_size
    end = start + page_size
    
    # Search
    search = request.GET.get('search', '')
    if search:
        # Normalize phone number for search - handle different formats
        normalized_search = search.replace(' ', '').replace('-', '').replace('+', '')
        # If search looks like a phone number starting with 0, also try with 251 prefix
        phone_search_variants = [search]
        if normalized_search.isdigit() and normalized_search.startswith('0'):
            phone_search_variants.append('251' + normalized_search[1:])
        
        phone_query = Q()
        for variant in phone_search_variants:
            phone_query |= Q(profile__phone_number__icontains=variant)
        
        users = users.filter(
            Q(username__icontains=search) | 
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            phone_query
        )
    
    total = users.count()
    users_page = users[start:end]
    
    data = [{
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'phone': mask_phone_number(user.profile.phone_number) if hasattr(user, 'profile') and user.profile.phone_number else None,
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
admin_users_list.view_class.required_permission = 'view_users'

@api_view(['GET'])
@permission_classes([HasAdminPermission])
def admin_user_detail(request, user_id):
    """Get detailed user information"""
    try:
        user = User.objects.select_related('profile').annotate(
            reel_count=Count('reels'),
            follower_count=Count('followers'),
            following_count=Count('following'),
            total_votes=Sum('reels__votes')
        ).get(id=user_id)
        
        # Debug: print counts
        print(f'[ADMIN] User detail: {user.username}, reels: {user.reel_count}, followers: {user.follower_count}, following: {user.following_count}, total_votes: {user.total_votes}')
        print(f'[ADMIN] Direct count - reels: {user.reels.count()}, followers: {user.followers.count()}, following: {user.following.count()}')
        
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
@permission_classes([HasAdminPermission])
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
admin_user_update.view_class.required_permission = 'edit_users'

@api_view(['DELETE'])
@permission_classes([HasAdminPermission])
def admin_user_delete(request, user_id):
    """Delete a user"""
    try:
        user = User.objects.get(id=user_id)
        username = user.username
        user.delete()
        return Response({'message': f'User {username} deleted successfully'})
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
admin_user_delete.view_class.required_permission = 'delete_users'

@api_view(['GET'])
@permission_classes([HasAdminPermission])
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

    # Media as every other client gets it (reel_media_payload): processed
    # files are stored as their full OBS URL, which FieldFile.url would mangle
    # into a key, and a video's picture is its `thumbnail` -- `image` is only
    # ever a photo's.
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
        **reel_media_payload(reel, request),
        'is_hidden': reel.is_hidden,
        'created_at': reel.created_at
    } for reel in reels_page]
    
    return Response({
        'reels': data,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size
    })
admin_reels_list.view_class.required_permission = 'view_content'

@api_view(['DELETE'])
@permission_classes([HasAdminPermission])
def admin_reel_delete(request, reel_id):
    """Delete a reel"""
    try:
        reel = Reel.objects.get(id=reel_id)
        reel.delete()
        return Response({'message': 'Reel deleted successfully'})
    except Reel.DoesNotExist:
        return Response({'error': 'Reel not found'}, status=status.HTTP_404_NOT_FOUND)
admin_reel_delete.view_class.required_permission = 'moderate_content'


def _log_admin_action(request, action, target_user=None, target_object=None, details=None):
    """Log an admin action: admin name, action, target, IP, timestamp, details."""
    from api.models.admin import SystemLog

    log_details = {
        'ip': request.META.get('REMOTE_ADDR'),
        'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200],
    }
    if target_user:
        log_details['target_user_id'] = target_user.id
        log_details['target_username'] = target_user.username
        log_details['target_email'] = target_user.email or ''
    if target_object:
        log_details['target_object_id'] = getattr(target_object, 'id', None)
        log_details['target_object_type'] = target_object.__class__.__name__
    if details:
        log_details.update(details)

    SystemLog.objects.create(
        log_type='admin_action', message=f'{action} by {request.user.username}',
        user=request.user, details=log_details,
    )


@api_view(['GET'])
@permission_classes([HasAdminPermission])
def admin_reel_detail(request, reel_id):
    """Get detailed information about a single reel for moderation"""
    from api.models import Report

    try:
        reel = Reel.objects.select_related('user', 'user__profile', 'campaign').annotate(
            comment_count=Count('comments', distinct=True),
            save_count=Count('saved_by', distinct=True),
            vote_count_db=Count('reel_votes', distinct=True),
            report_count=Count('reports', distinct=True),
        ).get(id=reel_id)
    except Reel.DoesNotExist:
        return Response({'error': 'Reel not found'}, status=status.HTTP_404_NOT_FOUND)

    profile = getattr(reel.user, 'profile', None)
    follower_count = reel.user.followers.count()
    following_count = reel.user.following.count()
    post_count = reel.user.reels.count()

    profile_photo = None
    if profile and profile.profile_photo:
        try:
            profile_photo = profile.profile_photo.url
        except Exception:
            pass
    if not profile_photo and profile and profile.avatar:
        try:
            profile_photo = profile.avatar.url
        except Exception:
            pass

    recent_comments = Comment.objects.filter(reel=reel).select_related('user').order_by('-created_at')[:10]
    comments_data = [{
        'id': c.id, 'user': c.user.username, 'text': c.text, 'created_at': c.created_at.isoformat(),
    } for c in recent_comments]

    reports = Report.objects.filter(reported_reel=reel).select_related('reported_by').order_by('-created_at')
    reports_data = [{
        'id': r.id, 'report_type': r.report_type, 'description': r.description, 'status': r.status,
        'priority': r.priority, 'reported_by': r.reported_by.username, 'created_at': r.created_at.isoformat(),
    } for r in reports]

    return Response({
        'id': reel.id,
        'user': {
            'id': reel.user.id,
            'username': reel.user.username,
            'first_name': reel.user.first_name,
            'last_name': reel.user.last_name,
            'email': reel.user.email,
            'is_active': reel.user.is_active,
            'date_joined': reel.user.date_joined.isoformat(),
            'last_login': reel.user.last_login.isoformat() if reel.user.last_login else None,
            'profile_photo': profile_photo,
            'bio': profile.bio if profile else '',
            'follower_count': follower_count,
            'following_count': following_count,
            'post_count': post_count,
            'is_shadowbanned': profile.is_shadowbanned if profile else False,
            'coins': profile.coins if profile else 0,
            'level': profile.level if profile else 1,
        },
        'caption': reel.caption,
        'hashtags': reel.hashtags,
        'overlay_text': reel.overlay_text,
        'votes': reel.votes,
        'vote_count_db': reel.vote_count_db,
        'view_count': reel.view_count,
        'shares': reel.shares,
        'comment_count': reel.comment_count,
        'save_count': reel.save_count,
        'report_count': reel.report_count,
        # image, media, thumbnail, duration, renditions, media_type and
        # processing state, resolved the way the feed resolves them.
        **reel_media_payload(reel, request),
        'is_hidden': reel.is_hidden,
        'is_boosted': reel.is_boosted,
        'campaign': {'id': reel.campaign.id, 'title': reel.campaign.title} if reel.campaign else None,
        'created_at': reel.created_at.isoformat(),
        'comments': comments_data,
        'reports': reports_data,
    })
admin_reel_detail.view_class.required_permission = 'view_content'


@api_view(['POST'])
@permission_classes([HasAdminPermission])
def admin_reel_moderate(request, reel_id):
    """Approve or remove a reel (toggle is_hidden)"""
    try:
        reel = Reel.objects.get(id=reel_id)
    except Reel.DoesNotExist:
        return Response({'error': 'Reel not found'}, status=status.HTTP_404_NOT_FOUND)

    action = request.data.get('action')
    if action == 'approve':
        reel.is_hidden = False
        message = 'Reel approved and is now visible'
    elif action == 'remove':
        reel.is_hidden = True
        message = 'Reel removed and is now hidden'
    else:
        return Response({'error': 'Invalid action. Use "approve" or "remove"'}, status=status.HTTP_400_BAD_REQUEST)

    reel.save(update_fields=['is_hidden'])

    _log_admin_action(
        request, f'{action}d reel by {reel.user.username}', target_user=reel.user, target_object=reel,
        details={
            'action': f'reel_{action}', 'reel_id': reel_id, 'reel_owner': reel.user.username,
            'is_hidden': reel.is_hidden,
        },
    )

    return Response({'message': message, 'is_hidden': reel.is_hidden, 'reel_id': reel_id})
admin_reel_moderate.view_class.required_permission = 'moderate_content'

@api_view(['POST'])
@permission_classes([HasAdminPermission])
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
@permission_classes([HasAdminPermission])
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
@permission_classes([HasAdminPermission])
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
@permission_classes([HasAdminPermission])
def admin_comment_delete(request, comment_id):
    """Delete a comment"""
    try:
        comment = Comment.objects.get(id=comment_id)
        comment.delete()
        return Response({'message': 'Comment deleted successfully'})
    except Comment.DoesNotExist:
        return Response({'error': 'Comment not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([HasAdminPermission])
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
@permission_classes([HasAdminPermission])
def admin_wipe_all_posts(request):
    """Wipe all reels/posts and related data (comments, votes, saves, campaign entries)."""
    from api.models import CommentLike, CommentReply
    from api.models.campaign import CampaignEntry, CampaignVote, CampaignWinner, CampaignNotification
    
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


@api_view(['GET'])
@permission_classes([HasAdminPermission])
def admin_security_events(request):
    """List SecurityEvent rows for monitoring (written by
    common/middleware/security.py)."""
    from api.models.admin import SecurityEvent

    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 50))
        event_type = request.GET.get('event_type', '')
        severity = request.GET.get('severity', '')
        is_resolved = request.GET.get('is_resolved', '')

        events = SecurityEvent.objects.all()
        if event_type:
            events = events.filter(event_type=event_type)
        if severity:
            events = events.filter(severity=severity)
        if is_resolved:
            events = events.filter(is_resolved=is_resolved == 'true')

        total = events.count()
        start = (page - 1) * page_size
        events_page = events[start:start + page_size]

        data = [{
            'id': event.id,
            'event_type': event.event_type,
            'severity': event.severity,
            'username': event.username,
            'ip_address': str(event.ip_address) if event.ip_address else None,
            'user_agent': event.user_agent,
            'endpoint': event.endpoint,
            'page': event.page,
            'action': event.action,
            'details': event.details,
            'is_resolved': event.is_resolved,
            'timestamp': event.timestamp.isoformat() if event.timestamp else None,
        } for event in events_page]

        return Response({
            'events': data, 'total': total, 'page': page, 'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
        })
    except Exception:
        return Response({'events': [], 'total': 0, 'page': 1, 'page_size': 50, 'total_pages': 0})
admin_security_events.view_class.required_permission = 'view_security_events'


@api_view(['POST'])
@permission_classes([HasAdminPermission])
def admin_resolve_security_event(request, event_id):
    """Mark a security event as resolved"""
    from api.models.admin import SecurityEvent

    try:
        event = SecurityEvent.objects.get(id=event_id)
    except SecurityEvent.DoesNotExist:
        return Response({'error': 'Security event not found'}, status=status.HTTP_404_NOT_FOUND)

    event.is_resolved = True
    event.save(update_fields=['is_resolved'])

    _log_admin_action(
        request, f'Resolved security event: {event.event_type}',
        details={
            'action': 'security_event_resolve', 'event_id': event_id, 'event_type': event.event_type,
            'severity': event.severity, 'affected_user': event.username,
            'ip_address': str(event.ip_address) if event.ip_address else None,
        },
    )
    return Response({'message': 'Security event resolved'})
admin_resolve_security_event.view_class.required_permission = 'manage_security_events'


@api_view(['POST'])
@permission_classes([HasAdminPermission])
def admin_mark_all_security_events_read(request):
    """Mark all unresolved security events as resolved"""
    from api.models.admin import SecurityEvent

    updated = SecurityEvent.objects.filter(is_resolved=False).update(is_resolved=True)
    _log_admin_action(
        request, 'Marked all security events as read',
        details={'action': 'security_events_bulk_resolve', 'count': updated},
    )
    return Response({'message': f'Marked {updated} security events as resolved'})
admin_mark_all_security_events_read.view_class.required_permission = 'manage_security_events'


@api_view(['GET'])
@permission_classes([HasAdminPermission])
def admin_security_stats(request):
    """Security statistics for the admin dashboard"""
    from api.models.admin import SecurityEvent

    events_by_type = SecurityEvent.objects.values('event_type').annotate(count=Count('id'))
    events_by_severity = SecurityEvent.objects.values('severity').annotate(count=Count('id'))
    unresolved_count = SecurityEvent.objects.filter(is_resolved=False).count()
    recent_events = SecurityEvent.objects.filter(timestamp__gte=timezone.now() - timedelta(hours=24)).count()
    high_severity_events = SecurityEvent.objects.filter(
        severity__in=['HIGH', 'CRITICAL'], timestamp__gte=timezone.now() - timedelta(days=7),
    ).count()

    return Response({
        'events_by_type': list(events_by_type),
        'events_by_severity': list(events_by_severity),
        'unresolved_count': unresolved_count,
        'recent_events': recent_events,
        'high_severity_events': high_severity_events,
    })
admin_security_stats.view_class.required_permission = 'view_security_events'


@api_view(['POST'])
@permission_classes([HasAdminPermission])
def admin_log_security_event(request):
    """Log a security event reported by the frontend (e.g. a detected
    client-side tampering attempt)."""
    from api.models.admin import SecurityEvent

    event_type = request.data.get('event_type')
    if not event_type:
        return Response({'error': 'event_type is required'}, status=status.HTTP_400_BAD_REQUEST)

    SecurityEvent.objects.create(
        event_type=event_type,
        severity=request.data.get('severity', 'MEDIUM'),
        user=request.user,
        username=request.user.username,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        page=request.data.get('page', ''),
        details=str(request.data.get('details', '')),
    )
    return Response({'message': 'Security event logged'})
admin_log_security_event.view_class.required_permission = 'manage_security_events'


@api_view(['GET'])
@permission_classes([HasAdminPermission])
def admin_user_role(request, user_id):
    """Get admin role details for a user."""
    from api.models.subscription import AdminRole

    admin_role = AdminRole.objects.filter(user_id=user_id).first()
    if admin_role:
        return Response({
            'role': admin_role.role,
            'permission_level': admin_role.permission_level,
            'is_active': admin_role.is_active,
        })
    # 200 with null data rather than 404 -- "no admin role" is an expected
    # state for most users, not an error the frontend needs to branch on.
    return Response({'role': None, 'permission_level': None, 'is_active': None})
admin_user_role.view_class.required_permission = 'view_users'


@api_view(['GET'])
@permission_classes([HasAdminPermission])
def admin_user_logs(request, user_id):
    """Get privilege-audit log entries where this user was the target or the actor."""
    from api.models.admin import PrivilegeAuditLog

    logs = PrivilegeAuditLog.objects.filter(
        Q(target_user_id=user_id) | Q(performed_by_id=user_id)
    ).order_by('-timestamp')[:50]

    return Response({
        'logs': [{
            'action': log.action,
            'target_user': log.target_user,
            'performed_by': log.performed_by,
            'details': log.details,
            'timestamp': log.timestamp.isoformat(),
        } for log in logs],
    })
admin_user_logs.view_class.required_permission = 'view_users'


@api_view(['POST'])
@permission_classes([HasAdminPermission])
def admin_grant_admin(request, user_id):
    """Grant or revoke admin privileges for a user with a role and permission level."""
    from api.models.admin import PrivilegeAuditLog
    from api.models.subscription import AdminRole

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    action = request.data.get('action', 'grant')

    if action == 'revoke':
        AdminRole.objects.filter(user=user).delete()
        user.is_staff = False
        user.is_superuser = False
        user.save()

        # Master declares this model but never writes to it anywhere, so
        # admin_user_logs/admin_privilege_audit always render empty -- a
        # dead audit trail for exactly the kind of action it exists to
        # record. Writing it here is the fix, not a deviation from intent.
        PrivilegeAuditLog.objects.create(
            action='REVOKE', target_user=user.username, target_user_id=user.id,
            performed_by=request.user.username, performed_by_id=request.user.id,
            details=f'Revoked admin privileges from {user.username}',
        )
        _log_admin_action(
            request, f'Revoked admin privileges from {user.username}', target_user=user,
            details={'action': 'admin_revoke', 'was_staff': True, 'was_superuser': True},
        )

        return Response({
            'message': 'Admin privileges revoked successfully',
            'user_id': user.id, 'username': user.username, 'is_staff': user.is_staff,
        })

    role = request.data.get('role', 'support_agent')
    permission_level = request.data.get('permission_level', 'read_only')

    admin_role, created = AdminRole.objects.update_or_create(
        user=user, defaults={'role': role, 'permission_level': permission_level, 'is_active': True},
    )

    user.is_staff = True
    user.is_superuser = (role == 'super_admin')
    user.save()

    PrivilegeAuditLog.objects.create(
        action='GRANT', target_user=user.username, target_user_id=user.id,
        performed_by=request.user.username, performed_by_id=request.user.id,
        details=f'Granted {role} ({permission_level}) to {user.username}',
    )
    _log_admin_action(
        request, f'Granted admin privileges to {user.username}', target_user=user,
        details={
            'action': 'admin_grant', 'role': role, 'permission_level': permission_level,
            'is_superuser': user.is_superuser, 'was_new_role': created,
        },
    )

    return Response({
        'message': 'Admin privileges granted successfully',
        'user_id': user.id, 'username': user.username, 'role': role,
        'permission_level': permission_level, 'is_staff': user.is_staff,
    })
admin_grant_admin.view_class.required_permission = 'manage_admins'


@api_view(['GET'])
@permission_classes([HasAdminPermission])
def admin_privilege_audit(request):
    """Paginated privilege-audit log across all admin grant/revoke actions.

    Master gates this behind bare IsAdminUser (any is_staff=True account),
    which would let e.g. a content_moderator read every admin grant/revoke
    action -- including target/performer phone numbers and emails. Gated
    behind HasAdminPermission('manage_admins') instead, matching
    admin_grant_admin: only super_admin (and whoever else is explicitly
    granted manage_admins) can see this trail, since seeing it is nearly as
    sensitive as being in it.
    """
    from api.models.admin import PrivilegeAuditLog

    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))

    logs = PrivilegeAuditLog.objects.order_by('-timestamp')
    total = logs.count()

    start = (page - 1) * page_size
    logs_page = logs[start:start + page_size]

    user_ids = set()
    for log in logs_page:
        user_ids.add(log.target_user_id)
        user_ids.add(log.performed_by_id)

    users = {u.id: u for u in User.objects.filter(id__in=user_ids).select_related('profile')}

    data = []
    for log in logs_page:
        target_user = users.get(log.target_user_id)
        performed_by = users.get(log.performed_by_id)

        target_user_phone = mask_phone_number(getattr(target_user.profile, 'phone_number', None)) if target_user and hasattr(target_user, 'profile') else None
        performed_by_phone = mask_phone_number(getattr(performed_by.profile, 'phone_number', None)) if performed_by and hasattr(performed_by, 'profile') else None

        data.append({
            'id': log.id,
            'timestamp': log.timestamp.isoformat() if log.timestamp else None,
            'action': log.action,
            'target_user': target_user.username if target_user else None,
            'target_user_id': log.target_user_id,
            'target_user_email': target_user.email if target_user else None,
            'target_user_phone': target_user_phone,
            'performed_by': performed_by.username if performed_by else None,
            'performed_by_id': log.performed_by_id,
            'performed_by_email': performed_by.email if performed_by else None,
            'performed_by_phone': performed_by_phone,
            'details': log.details,
        })

    return Response({
        'logs': data,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size if page_size else 0,
    })
admin_privilege_audit.view_class.required_permission = 'manage_admins'
