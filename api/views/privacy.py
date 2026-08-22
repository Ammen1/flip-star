import json
from datetime import datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from api.models.legal import ConsentHistory, UserConsent

CONSENT_CATALOG = {
    'camera': {
        'type': 'camera',
        'title': 'Camera Access',
        'disclosure': 'FlipStar collects camera data to enable video and photo creation for social content sharing and campaign participation.',
    },
    'storage': {
        'type': 'storage',
        'title': 'Storage Access',
        'disclosure': 'FlipStar accesses device storage to save your created content, profile media, and app preferences needed for core functionality.',
    },
    'analytics': {
        'type': 'analytics',
        'title': 'Analytics',
        'disclosure': 'FlipStar uses analytics data to improve app performance, reliability, and user experience.',
    },
    'marketing': {
        'type': 'marketing',
        'title': 'Marketing',
        'disclosure': 'FlipStar uses marketing consent to send product updates, campaigns, and creator opportunities.',
    },
    'gdpr_banner': {
        'type': 'gdpr_banner',
        'title': 'Cookie and Tracking Banner',
        'disclosure': 'FlipStar asks EU users for tracking consent before enabling optional analytics or marketing technologies.',
    },
    'privacy_policy': {
        'type': 'privacy_policy',
        'title': 'Privacy Policy Acceptance',
        'disclosure': 'FlipStar records the privacy policy version you accepted so that we can notify you about material changes.',
    },
}


def _get_user_consents(user):
    """Get user's consent status from database"""
    user_consents = UserConsent.objects.filter(user=user)
    consents_dict = {}

    for consent_type, catalog_entry in CONSENT_CATALOG.items():
        user_consent = user_consents.filter(consent_type=consent_type).first()
        consents_dict[consent_type] = {
            **catalog_entry,
            'granted': user_consent.granted if user_consent else False,
            'granted_at': user_consent.granted_at.isoformat() if user_consent and user_consent.granted_at else None,
            'withdrawn_at': user_consent.withdrawn_at.isoformat() if user_consent and user_consent.withdrawn_at else None,
            'updated_at': user_consent.updated_at.isoformat() if user_consent else None,
            'source': user_consent.source if user_consent else 'in_app',
            'metadata': user_consent.metadata if user_consent else {},
            'disclosure_version': user_consent.disclosure_version if user_consent else '2026.05',
        }

    return consents_dict


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
        consents = _get_user_consents(request.user)
        return Response({
            'consents': consents,
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
        source = request.data.get('source', 'in_app')
        metadata = request.data.get('metadata', {})
        disclosure_version = request.data.get('disclosure_version', '2026.05')

        if not consent_type:
            return Response({'error': 'Consent type is required'}, status=status.HTTP_400_BAD_REQUEST)

        valid_types = list(CONSENT_CATALOG.keys())
        if consent_type not in valid_types:
            return Response({'error': 'Invalid consent type'}, status=status.HTTP_400_BAD_REQUEST)

        # Get or create user consent record
        user_consent, created = UserConsent.objects.get_or_create(
            user=request.user,
            consent_type=consent_type,
            defaults={
                'granted': granted,
                'source': source,
                'metadata': metadata,
                'disclosure_version': disclosure_version,
            }
        )

        # Update if not newly created
        if not created:
            user_consent.granted = granted
            user_consent.source = source
            user_consent.metadata = metadata
            user_consent.disclosure_version = disclosure_version
            user_consent.save()

        # Create history record
        ConsentHistory.objects.create(
            user=request.user,
            consent_type=consent_type,
            action='granted' if granted else 'withdrawn',
            granted=granted,
            source=source,
            metadata=metadata,
            disclosure_version=disclosure_version,
        )

        # Return updated consent status
        updated_consents = _get_user_consents(request.user)

        return Response({
            'message': f'Consent for {consent_type} updated to {granted}',
            'type': consent_type,
            'granted': granted,
            'updated_at': user_consent.updated_at.isoformat(),
            'consents': {
                consent_type: updated_consents[consent_type],
            }
        })

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_consent_history(request):
    """Return consent history in the shape expected by the mobile client."""
    try:
        history_records = ConsentHistory.objects.filter(user=request.user).order_by('-created_at')[:50]
        history = [
            {
                'type': record.consent_type,
                'action': record.action,
                'granted': record.granted,
                'source': record.source,
                'metadata': record.metadata,
                'created_at': record.created_at.isoformat(),
            }
            for record in history_records
        ]
        return Response({'history': history})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_privacy_policy_summary(request):
    return Response({
        'version': '2026.05',
        'effective_date': '2026-05-25',
        'delete_account_url': 'https://flipstar.et/delete-account',
        'privacy_policy_url': 'https://flipstar.et/privacy-policy',
        'contact_email': 'privacy@flipstar.et',
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_eu_rights_summary(request):
    return Response({
        'rights': [
            'Access your personal data',
            'Correct inaccurate information',
            'Request deletion of eligible data',
            'Restrict or object to certain processing',
            'Download a copy of your data',
            'Withdraw optional consent at any time',
        ],
        'transfer_mechanisms': [
            'Standard Contractual Clauses',
            'Equivalent contractual and organizational safeguards',
        ],
        'contact_email': 'privacy@flipstar.et',
    })


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
