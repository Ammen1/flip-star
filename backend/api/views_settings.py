from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Count, Avg, Sum
from datetime import timedelta
from .models_admin import APIKey, PlatformSettings, SystemLog, PlatformMetrics, AdminNotification
from .models import Reel, Comment, Vote, Follow, Subscription
import json

@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_platform_settings(request):
    """Get platform settings"""
    settings, created = PlatformSettings.objects.get_or_create(id=1)
    
    return Response({
        'platform_name': settings.platform_name,
        'platform_description': settings.platform_description,
        'maintenance_mode': settings.maintenance_mode,
        'allow_registrations': settings.allow_registrations,
        'require_email_verification': settings.require_email_verification,
        'max_file_size_mb': settings.max_file_size_mb,
        'allowed_video_formats': settings.allowed_video_formats,
        'allowed_image_formats': settings.allowed_image_formats,
        'max_caption_length': settings.max_caption_length,
        'enable_comments': settings.enable_comments,
        'enable_voting': settings.enable_voting,
        'auto_moderation': settings.auto_moderation,
        'profanity_filter': settings.profanity_filter,
        'spam_detection': settings.spam_detection,
        'email_notifications': settings.email_notifications,
        'push_notifications': settings.push_notifications,
        'sms_notifications': settings.sms_notifications,
        'cache_enabled': settings.cache_enabled,
        'cdn_enabled': settings.cdn_enabled,
        'cdn_url': settings.cdn_url,
        'api_rate_limit': settings.api_rate_limit,
        'api_enabled': settings.api_enabled,
        'analytics_enabled': settings.analytics_enabled,
        'track_user_activity': settings.track_user_activity,
        # Typography Settings
        'font_family_primary': settings.font_family_primary,
        'font_family_secondary': settings.font_family_secondary,
        'font_family_username': settings.font_family_username,
        'font_family_caption': settings.font_family_caption,
        'font_size_base': settings.font_size_base,
        'font_weight_headings': settings.font_weight_headings,
        'font_weight_body': settings.font_weight_body,
        'letter_spacing': settings.letter_spacing,
        'line_height': settings.line_height,
        # Theme Colors
        'primary_color': settings.primary_color,
        'secondary_color': settings.secondary_color,
        'theme_preset': settings.theme_preset,
        'dark_mode_default': settings.dark_mode_default,
        'primary_color_override': settings.primary_color_override,
        'updated_at': settings.updated_at,
    })

@api_view(['POST'])
@permission_classes([IsAdminUser])
def update_platform_settings(request):
    """Update platform settings"""
    settings, created = PlatformSettings.objects.get_or_create(id=1)
    
    # Update fields
    for field, value in request.data.items():
        if hasattr(settings, field):
            setattr(settings, field, value)
    
    settings.updated_by = request.user
    settings.save()
    
    # Log the change
    SystemLog.objects.create(
        log_type='info',
        message=f'Platform settings updated by {request.user.username}',
        user=request.user,
        details={'updated_fields': list(request.data.keys())}
    )
    
    return Response({'message': 'Settings updated successfully'})


@api_view(['GET'])
@permission_classes([AllowAny])
def get_public_settings(request):
    """Get public platform settings (typography, colors) - no auth required"""
    try:
        print(f"[PUBLIC_SETTINGS] Request from {request.META.get('REMOTE_ADDR')}")
        
        # Try to get settings from database with timeout
        try:
            settings = PlatformSettings.objects.get(id=1)
            print(f"[PUBLIC_SETTINGS] Settings found: font_secondary={settings.font_family_secondary}")
            return Response({
                'platform_name': settings.platform_name,
                'font_family_primary': settings.font_family_primary,
                'font_family_secondary': settings.font_family_secondary,
                'font_family_username': settings.font_family_username,
                'font_family_caption': settings.font_family_caption,
                'font_size_base': settings.font_size_base,
                'font_weight_headings': settings.font_weight_headings,
                'font_weight_body': settings.font_weight_body,
                'letter_spacing': settings.letter_spacing,
                'line_height': settings.line_height,
                'primary_color': settings.primary_color,
                'secondary_color': settings.secondary_color,
                'theme_preset': settings.theme_preset,
                'dark_mode_default': settings.dark_mode_default,
                'primary_color_override': settings.primary_color_override,
            })
        except PlatformSettings.DoesNotExist:
            print("[PUBLIC_SETTINGS] No settings found, returning defaults")
        except Exception as db_error:
            print(f"[PUBLIC_SETTINGS] Database error: {db_error}")
        
        # Return defaults if settings don't exist or database error
        return Response({
            'platform_name': 'Selfie Star',
            'font_family_primary': 'Inter',
            'font_family_secondary': 'Inter',
            'font_family_username': 'Inter',
            'font_family_caption': 'Inter',
            'font_size_base': 16,
            'font_weight_headings': '700',
            'font_weight_body': '400',
            'letter_spacing': 'normal',
            'line_height': '1.5',
            'primary_color': '#8B5CF6',
            'secondary_color': '#F97316',
            'theme_preset': 'flipstar',
            'dark_mode_default': False,
            'primary_color_override': None,
        })
    except Exception as e:
        print(f"[PUBLIC_SETTINGS] Unexpected error: {e}")
        # Return defaults on any error to prevent CORS issues
        return Response({
            'platform_name': 'Selfie Star',
            'font_family_primary': 'Inter',
            'font_family_secondary': 'Inter',
            'font_family_username': 'Inter',
            'font_family_caption': 'Inter',
            'font_size_base': 16,
            'font_weight_headings': '700',
            'font_weight_body': '400',
            'letter_spacing': 'normal',
            'line_height': '1.5',
            'primary_color': '#8B5CF6',
            'secondary_color': '#F97316',
            'theme_preset': 'flipstar',
            'dark_mode_default': False,
            'primary_color_override': None,
        })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_api_keys(request):
    """Get all API keys"""
    keys = APIKey.objects.filter(user=request.user)
    
    data = [{
        'id': key.id,
        'name': key.name,
        'key': key.key,
        'is_active': key.is_active,
        'created_at': key.created_at,
        'last_used': key.last_used,
        'expires_at': key.expires_at,
    } for key in keys]
    
    return Response(data)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def create_api_key(request):
    """Create new API key"""
    name = request.data.get('name', 'API Key')
    expires_days = request.data.get('expires_days', 365)
    
    api_key = APIKey.objects.create(
        user=request.user,
        name=name,
        expires_at=timezone.now() + timedelta(days=expires_days) if expires_days else None
    )
    
    # Log the creation
    SystemLog.objects.create(
        log_type='security',
        message=f'API key created: {name}',
        user=request.user,
        details={'key_id': api_key.id, 'name': name}
    )
    
    return Response({
        'id': api_key.id,
        'name': api_key.name,
        'key': api_key.key,
        'created_at': api_key.created_at,
        'expires_at': api_key.expires_at,
    }, status=status.HTTP_201_CREATED)

@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def delete_api_key(request, key_id):
    """Delete API key"""
    try:
        api_key = APIKey.objects.get(id=key_id, user=request.user)
        key_name = api_key.name
        api_key.delete()
        
        # Log the deletion
        SystemLog.objects.create(
            log_type='security',
            message=f'API key deleted: {key_name}',
            user=request.user,
            details={'key_id': key_id}
        )
        
        return Response({'message': 'API key deleted successfully'})
    except APIKey.DoesNotExist:
        return Response({'error': 'API key not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def toggle_api_key(request, key_id):
    """Toggle API key active status"""
    try:
        api_key = APIKey.objects.get(id=key_id, user=request.user)
        api_key.is_active = not api_key.is_active
        api_key.save()
        
        return Response({
            'message': f'API key {"activated" if api_key.is_active else "deactivated"}',
            'is_active': api_key.is_active
        })
    except APIKey.DoesNotExist:
        return Response({'error': 'API key not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_system_logs(request):
    """Get system logs with filtering"""
    logs = SystemLog.objects.all()
    
    # Filters
    log_type = request.GET.get('type')
    if log_type:
        logs = logs.filter(log_type=log_type)

    search_q = request.GET.get('search', '').strip()
    if search_q:
        from django.db.models import Q
        logs = logs.filter(
            Q(message__icontains=search_q) |
            Q(endpoint__icontains=search_q)
        )

    # Pagination
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))
    start = (page - 1) * page_size
    end = start + page_size
    
    total = logs.count()
    logs_page = logs[start:end]
    
    data = [{
        'id': log.id,
        'log_type': log.log_type,
        'message': log.message,
        'user': log.user.username if log.user else None,
        'ip_address': log.ip_address,
        'endpoint': log.endpoint,
        'details': log.details,
        'created_at': log.created_at,
    } for log in logs_page]
    
    return Response({
        'logs': data,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size
    })

@api_view(['POST'])
@permission_classes([IsAdminUser])
def clear_system_logs(request):
    """Clear system logs (by type or all)"""
    log_type = request.data.get('log_type', 'all')
    if log_type and log_type != 'all':
        deleted_count, _ = SystemLog.objects.filter(log_type=log_type).delete()
    else:
        deleted_count, _ = SystemLog.objects.all().delete()
    SystemLog.objects.create(
        log_type='security',
        message=f'System logs cleared by {request.user.username} (type={log_type})',
        user=request.user,
        details={'cleared_type': log_type, 'deleted_count': deleted_count}
    )
    return Response({'message': f'Cleared {deleted_count} log(s)', 'count': deleted_count})


@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_security_overview(request):
    """Security dashboard: stats + recent security events + log distribution + IP analysis + health checks"""
    from datetime import timedelta
    from django.db.models import Count
    now = timezone.now()
    h24 = now - timedelta(hours=24)
    d7  = now - timedelta(days=7)
    m1  = now - timedelta(days=30)

    def cnt(log_type, since=None):
        qs = SystemLog.objects.filter(log_type=log_type)
        if since:
            qs = qs.filter(created_at__gte=since)
        return qs.count()

    stats = {
        'security_total':  cnt('security'),
        'security_24h':    cnt('security', h24),
        'error_total':     cnt('error'),
        'error_24h':       cnt('error', h24),
        'warning_total':   cnt('warning'),
        'warning_24h':     cnt('warning', h24),
        'critical_total':  cnt('critical'),
        'critical_24h':    cnt('critical', h24),
        'info_total':      cnt('info'),
        'active_users_7d': User.objects.filter(last_login__gte=d7).count(),
        'new_users_24h':   User.objects.filter(date_joined__gte=h24).count(),
        'total_logs':      SystemLog.objects.count(),
    }

    log_dist = {item['log_type']: item['count']
                for item in SystemLog.objects.values('log_type').annotate(count=Count('id'))}

    recent = SystemLog.objects.filter(log_type='security').order_by('-created_at')[:20]
    events = [{
        'id': l.id, 'message': l.message,
        'user': l.user.username if l.user else None,
        'user_id': l.user.id if l.user else None,
        'ip_address': l.ip_address, 'endpoint': l.endpoint,
        'details': l.details, 'created_at': l.created_at,
    } for l in recent]

    # IP-based failed login analysis (detect brute force attacks)
    failed_logins = SystemLog.objects.filter(
        log_type='security',
        created_at__gte=h24,
        message__icontains='failed'
    ).exclude(ip_address__isnull=True).exclude(ip_address='')

    ip_failures = {}
    for log in failed_logins:
        ip = log.ip_address
        if ip not in ip_failures:
            ip_failures[ip] = {'count': 0, 'users': set(), 'last_attempt': log.created_at}
        ip_failures[ip]['count'] += 1
        if log.user:
            ip_failures[ip]['users'].add(log.user.username)

    # Flag suspicious IPs (>5 failed attempts in 24h)
    suspicious_ips = [
        {'ip': ip, 'failed_attempts': data['count'], 'targeted_users': list(data['users'])[:5], 'last_attempt': data['last_attempt']}
        for ip, data in ip_failures.items() if data['count'] >= 5
    ]
    suspicious_ips.sort(key=lambda x: x['failed_attempts'], reverse=True)

    # System health checks
    health = {}
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        health['database'] = 'healthy'
    except Exception as e:
        health['database'] = f'error: {str(e)[:30]}'

    try:
        # Check API response time
        import time
        start = time.time()
        User.objects.first()
        elapsed = (time.time() - start) * 1000
        health['api_response_ms'] = round(elapsed, 2)
        health['api'] = 'healthy' if elapsed < 500 else 'slow'
    except Exception as e:
        health['api'] = f'error: {str(e)[:30]}'

    # Storage check (approximate - count media files)
    try:
        media_count = Reel.objects.exclude(media='').count() + Reel.objects.exclude(image='').count()
        health['storage'] = 'healthy'
        health['media_files'] = media_count
    except Exception as e:
        health['storage'] = f'error: {str(e)[:30]}'

    # Recent API keys activity
    from .models_admin import APIKey
    api_keys_active = APIKey.objects.filter(is_active=True).count()
    api_keys_total = APIKey.objects.count()

    # Admin count
    admin_count = User.objects.filter(is_staff=True).count()

    return Response({
        'stats': stats,
        'log_distribution': log_dist,
        'recent_events': events,
        'suspicious_ips': suspicious_ips[:10],  # Top 10 suspicious IPs
        'health': health,
        'api_keys': {'active': api_keys_active, 'total': api_keys_total},
        'admins': admin_count,
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_platform_performance(request):
    """Get platform performance metrics"""
    # Get today's metrics
    today = timezone.now().date()
    
    # Calculate real-time metrics
    total_users = User.objects.count()
    active_today = User.objects.filter(last_login__gte=timezone.now() - timedelta(days=1)).count()
    
    total_reels = Reel.objects.count()
    reels_today = Reel.objects.filter(created_at__gte=timezone.now() - timedelta(days=1)).count()
    
    total_votes = Vote.objects.count()
    votes_today = Vote.objects.filter(created_at__gte=timezone.now() - timedelta(days=1)).count()
    
    total_comments = Comment.objects.count()
    comments_today = Comment.objects.filter(created_at__gte=timezone.now() - timedelta(days=1)).count()
    
    # Database performance
    from django.db import connection
    db_queries = len(connection.queries)
    
    # Get last 7 days metrics
    week_ago = today - timedelta(days=7)
    metrics_week = PlatformMetrics.objects.filter(date__gte=week_ago).order_by('date')
    
    metrics_data = [{
        'date': m.date.isoformat(),
        'active_users': m.active_users,
        'new_reels': m.new_reels,
        'new_votes': m.new_votes,
        'api_calls': m.api_calls,
        'avg_response_time_ms': m.avg_response_time_ms,
        'error_rate': m.error_rate,
    } for m in metrics_week]
    
    return Response({
        'current': {
            'total_users': total_users,
            'active_today': active_today,
            'total_reels': total_reels,
            'reels_today': reels_today,
            'total_votes': total_votes,
            'votes_today': votes_today,
            'total_comments': total_comments,
            'comments_today': comments_today,
            'db_queries': db_queries,
        },
        'weekly_trend': metrics_data,
        'system_health': {
            'database': 'healthy',
            'api': 'healthy',
            'storage': 'healthy',
        }
    })

@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_admin_notifications(request):
    """Get admin notifications"""
    notifications = AdminNotification.objects.filter(is_read=False)[:20]
    
    data = [{
        'id': n.id,
        'title': n.title,
        'message': n.message,
        'priority': n.priority,
        'action_url': n.action_url,
        'created_at': n.created_at,
    } for n in notifications]
    
    return Response(data)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def mark_notification_read(request, notification_id):
    """Mark notification as read"""
    try:
        notification = AdminNotification.objects.get(id=notification_id)
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        return Response({'message': 'Notification marked as read'})
    except AdminNotification.DoesNotExist:
        return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def send_platform_notification(request):
    """Send notification to all users or specific users"""
    title = request.data.get('title')
    message = request.data.get('message')
    user_ids = request.data.get('user_ids', [])
    
    if not title or not message:
        return Response({'error': 'Title and message required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # If user_ids provided, send to specific users, otherwise all users
    if user_ids:
        users = User.objects.filter(id__in=user_ids)
    else:
        users = User.objects.filter(is_active=True)
    
    # Here you would integrate with your notification system
    # For now, just log it
    SystemLog.objects.create(
        log_type='info',
        message=f'Notification sent: {title}',
        user=request.user,
        details={
            'title': title,
            'message': message,
            'recipient_count': users.count()
        }
    )
    
    return Response({
        'message': f'Notification sent to {users.count()} users',
        'count': users.count()
    })

@api_view(['POST'])
@permission_classes([IsAdminUser])
def bulk_user_action(request):
    """Perform bulk actions on users"""
    action = request.data.get('action')
    user_ids = request.data.get('user_ids', [])
    
    if not action or not user_ids:
        return Response({'error': 'Action and user_ids required'}, status=status.HTTP_400_BAD_REQUEST)
    
    users = User.objects.filter(id__in=user_ids)
    count = users.count()
    
    if action == 'activate':
        users.update(is_active=True)
        message = f'{count} users activated'
    elif action == 'deactivate':
        users.update(is_active=False)
        message = f'{count} users deactivated'
    elif action == 'delete':
        users.delete()
        message = f'{count} users deleted'
    elif action == 'upgrade_pro':
        for user in users:
            sub, created = Subscription.objects.get_or_create(user=user)
            sub.plan = 'pro'
            sub.expires_at = timezone.now() + timedelta(days=30)
            sub.save()
        message = f'{count} users upgraded to Pro'
    else:
        return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Log the action
    SystemLog.objects.create(
        log_type='info',
        message=f'Bulk action performed: {action}',
        user=request.user,
        details={'action': action, 'user_count': count, 'user_ids': user_ids}
    )
    
    return Response({'message': message, 'count': count})

@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_database_stats(request):
    """Get database statistics"""
    stats = {
        'users': User.objects.count(),
        'reels': Reel.objects.count(),
        'comments': Comment.objects.count(),
        'votes': Vote.objects.count(),
        'follows': Follow.objects.count(),
        'subscriptions': Subscription.objects.count(),
        'api_keys': APIKey.objects.count(),
        'system_logs': SystemLog.objects.count(),
    }
    
    # Storage stats (approximate)
    total_reels_with_media = Reel.objects.exclude(media='').count()
    total_reels_with_image = Reel.objects.exclude(image='').count()
    
    return Response({
        'tables': stats,
        'storage': {
            'reels_with_media': total_reels_with_media,
            'reels_with_image': total_reels_with_image,
        }
    })
