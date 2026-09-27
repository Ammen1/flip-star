"""Web Push subscription endpoints (VAPID).

- GET  /api/push/public-key/         → returns the VAPID public key (anyone).
- POST /api/push/subscribe/          → save or update a PushSubscription for
                                       the authenticated user. Body matches the
                                       PushSubscription JSON returned by
                                       browser PushManager.subscribe().toJSON().
- POST /api/push/unsubscribe/        → remove a subscription by endpoint.
"""

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.integrations.push.endpoints import PushEndpointRejected, validate_push_endpoint
from api.models import PushSubscription
from common.security import encrypted_endpoint


@api_view(['GET'])
@permission_classes([AllowAny])
@encrypted_endpoint
def push_public_key(request):
    return Response({'public_key': settings.VAPID_PUBLIC_KEY or ''})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def push_subscribe(request):
    data = request.data or {}
    endpoint = data.get('endpoint')
    keys = data.get('keys') or {}
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')
    if not endpoint or not p256dh or not auth:
        return Response(
            {'error': 'endpoint, keys.p256dh and keys.auth are required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Audit finding H-07. This endpoint used to store any URL the caller sent,
    # and the server later POSTed to it -- a user-controlled outbound
    # destination, with egress unrestricted at the NetworkPolicy level. The
    # destination is checked before it is persisted, so an unacceptable one
    # never reaches the database, and api/integrations/push/webpush.py checks
    # again before sending in case a stored row predates this or the allow-list
    # has since narrowed.
    try:
        endpoint = validate_push_endpoint(endpoint)
    except PushEndpointRejected as exc:
        return Response(
            {'error': 'Push endpoint is not a supported push service.', 'code': exc.reason},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:255]
    sub, created = PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            'user': request.user,
            'p256dh': p256dh,
            'auth': auth,
            'user_agent': user_agent,
        },
    )
    return Response({'ok': True, 'created': created, 'id': sub.id})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def push_unsubscribe(request):
    endpoint = (request.data or {}).get('endpoint')
    if not endpoint:
        return Response({'error': 'endpoint is required'}, status=status.HTTP_400_BAD_REQUEST)
    deleted, _ = PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
    return Response({'ok': True, 'deleted': deleted})
