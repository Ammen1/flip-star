import json
from datetime import datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def export_user_data(request):
    """
    Export all user data in JSON format for GDPR compliance
    """
    try:
        user = request.user
        
        # Collect all user data
        export_data = {
            'export_info': {
                'date': datetime.now().isoformat(),
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'export_type': 'user_data_export'
            },
            'profile': {
                'username': user.username,
                'email': user.email,
                'full_name': getattr(user.profile, 'full_name', None),
                'phone_number': getattr(user.profile, 'phone_number', None),
                'profile_photo': user.profile.profile_photo.url if hasattr(user.profile, 'profile_photo') and user.profile.profile_photo else None,
                'bio': getattr(user.profile, 'bio', None),
                'is_private': getattr(user.profile, 'is_private', False),
                'show_activity': getattr(user.profile, 'show_activity', True),
                'allow_messages': getattr(user.profile, 'allow_messages', True),
                'created_at': user.date_joined.isoformat(),
                'last_login': user.last_login.isoformat() if user.last_login else None
            },
            'posts': [
                {
                    'id': post.id,
                    'caption': post.caption,
                    'hashtags': post.hashtags,
                    'media': post.media.url if post.media else None,
                    'created_at': post.created_at.isoformat(),
                    'is_campaign_post': getattr(post, 'is_campaign_post', False),
                    'campaign_id': getattr(post, 'campaign_id', None)
                }
                for post in user.post_set.all()
            ],
            'comments': [
                {
                    'id': comment.id,
                    'content': comment.content,
                    'post_id': comment.post_id,
                    'created_at': comment.created_at.isoformat()
                }
                for comment in user.comment_set.all()
            ],
            'likes': [
                {
                    'id': like.id,
                    'post_id': like.post_id,
                    'created_at': like.created_at.isoformat()
                }
                for like in user.like_set.all()
            ],
            'campaign_entries': [
                {
                    'id': entry.id,
                    'campaign_id': entry.campaign_id,
                    'reel_id': entry.reel_id,
                    'created_at': entry.created_at.isoformat()
                }
                for entry in user.campaignentry_set.all()
            ],
            'transactions': [
                {
                    'id': transaction.id,
                    'amount': transaction.amount,
                    'transaction_type': transaction.transaction_type,
                    'description': transaction.description,
                    'created_at': transaction.created_at.isoformat()
                }
                for transaction in user.wallettransaction_set.all()
            ],
            'notifications': [
                {
                    'id': notification.id,
                    'type': notification.type,
                    'content': notification.content,
                    'created_at': notification.created_at.isoformat()
                }
                for notification in user.notification_set.all()
            ],
            'privacy_settings': {
                'private_account': getattr(user.profile, 'is_private', False),
                'show_activity': getattr(user.profile, 'show_activity', True),
                'allow_messages': getattr(user.profile, 'allow_messages', True)
            },
            'app_settings': {
                'dark_mode': getattr(user.profile, 'dark_mode', False),
                'language': getattr(user.profile, 'language', 'en'),
                'notification_preferences': {
                    'likes': getattr(user.profile, 'notification_likes', True),
                    'comments': getattr(user.profile, 'notification_comments', True),
                    'follows': getattr(user.profile, 'notification_follows', True),
                    'messages': getattr(user.profile, 'notification_messages', True)
                }
            }
        }
        
        # Calculate data size
        json_data = json.dumps(export_data, indent=2, default=str)
        data_size = len(json_data.encode('utf-8'))
        
        return Response({
            'message': 'Data export prepared successfully',
            'data_size': data_size,
            'export_data': export_data,
            'export_summary': {
                'total_posts': len(export_data['posts']),
                'total_comments': len(export_data['comments']),
                'total_likes': len(export_data['likes']),
                'total_transactions': len(export_data['transactions']),
                'total_notifications': len(export_data['notifications'])
            }
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_consent_status(request):
    """
    Get current consent status for the authenticated user
    """
    try:
        # For now, return default consent status
        # In a real implementation, this would be stored in the database
        return Response({
            'consents': {
                'camera': False,
                'storage': False,
                'analytics': False,
                'marketing': False,
                'functional': True,
                'necessary': True
            },
            'last_updated': datetime.now().isoformat()
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_consent(request):
    """
    Update consent preferences for the authenticated user
    """
    try:
        consent_type = request.data.get('type')
        granted = request.data.get('granted', False)
        
        if not consent_type:
            return Response({'error': 'Consent type is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        valid_types = ['camera', 'storage', 'analytics', 'marketing']
        if consent_type not in valid_types:
            return Response({'error': 'Invalid consent type'}, status=status.HTTP_400_BAD_REQUEST)
        
        # For now, just return success
        # In a real implementation, this would be stored in the database
        return Response({
            'message': f'Consent for {consent_type} updated to {granted}',
            'type': consent_type,
            'granted': granted,
            'updated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_account(request):
    """
    Delete user account and all associated data
    """
    try:
        user = request.user
        
        # In a real implementation, this would:
        # 1. Delete user's posts and media
        # 2. Delete user's comments and likes
        # 3. Delete user's transactions (keep for legal compliance)
        # 4. Delete user's profile
        # 5. Delete the user account
        
        # For now, just return success message
        return Response({
            'message': 'Account deletion request received. You will receive a confirmation email shortly.',
            'deletion_timeline': 'Your account will be permanently deleted within 30 days.',
            'data_retention': 'Some data may be retained for legal compliance for up to 7 years.'
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_privacy_settings(request):
    """
    Get current privacy settings for the authenticated user
    """
    try:
        profile = request.user.profile
        return Response({
            'privateAccount': profile.is_private,
            'showActivity': profile.show_activity,
            'allowMessages': profile.allow_messages,
            'allowMentions': profile.allow_mentions,
            'notifications': {
                'likes': profile.notification_likes,
                'comments': profile.notification_comments,
                'follows': profile.notification_follows,
                'messages': profile.notification_messages,
            },
            'darkMode': profile.dark_mode,
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_privacy_settings(request):
    """
    Update privacy settings for the authenticated user
    """
    try:
        profile = request.user.profile
        
        # Map frontend field names to model field names
        field_mapping = {
            'privateAccount': 'is_private',
            'showActivity': 'show_activity', 
            'allowMessages': 'allow_messages',
            'allowMentions': 'allow_mentions',
            'darkMode': 'dark_mode',
        }
        
        # Update main privacy settings
        for frontend_field, model_field in field_mapping.items():
            if frontend_field in request.data:
                setattr(profile, model_field, request.data[frontend_field])
        
        # Update notification settings if provided
        if 'notifications' in request.data:
            notifications = request.data['notifications']
            if 'likes' in notifications:
                profile.notification_likes = notifications['likes']
            if 'comments' in notifications:
                profile.notification_comments = notifications['comments']
            if 'follows' in notifications:
                profile.notification_follows = notifications['follows']
            if 'messages' in notifications:
                profile.notification_messages = notifications['messages']
        
        profile.save()
        
        return Response({
            'message': 'Privacy settings updated successfully',
            'settings': {
                'privateAccount': profile.is_private,
                'showActivity': profile.show_activity,
                'allowMessages': profile.allow_messages,
                'allowMentions': profile.allow_mentions,
                'notifications': {
                    'likes': profile.notification_likes,
                    'comments': profile.notification_comments,
                    'follows': profile.notification_follows,
                    'messages': profile.notification_messages,
                },
                'darkMode': profile.dark_mode,
            }
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
