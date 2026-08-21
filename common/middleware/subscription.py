"""
Subscription paywall middleware.

.. warning::

   **This middleware is not active and has never been active.** It was never
   listed in ``MIDDLEWARE``, so the subscription gate it implements has never
   run in any environment. It is preserved verbatim from ``api/middleware.py``
   because it documents intended product behaviour, not because it works.

   Two defects must be fixed before it can be enabled (audit finding M-02):

   1. ``process_request`` returns a DRF ``Response``. A bare ``Response`` has no
      renderer attached, so returning one from middleware raises
      ``ContentNotRenderedError``. It must return a ``JsonResponse``.
   2. It reads ``request.user``, which requires it to be ordered *after*
      ``AuthenticationMiddleware``.

   Enabling it is a product decision with revenue impact and is out of scope for
   a restructure.
"""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.utils.deprecation import MiddlewareMixin
from rest_framework import status
from rest_framework.response import Response

#: Path prefixes exempt from the subscription check.
EXEMPT_PATHS = [
    '/api/v1/auth/',
    '/api/v1/subscription/',
    '/api/v1/health/',
    '/api/v1/settings/public/',
    '/api/v1/posts/',
    '/api/v1/reels/',
    '/api/v1/profile/',
    '/api/v1/campaigns/',
    '/api/v1/search/',
    '/api/v1/explorer/',
    '/api/v1/follows/',
    '/api/v1/gamification/',
    '/api/v1/wallet/',
    '/api/v1/coins/',
    '/api/v1/messages/',
    '/admin/',
    '/media/',
    '/static/',
]

#: Endpoints always exempt, even when nested under a non-exempt prefix.
ALWAYS_EXEMPT_ENDPOINTS = [
    '/api/v1/posts/create',
    '/api/v1/reels/create',
    '/api/v1/comments/',
    '/api/v1/likes/',
    '/api/v1/gifts/',
    '/api/v1/follows/toggle',
    '/api/v1/saved/',
]

#: Read-only methods never require a subscription.
EXEMPT_METHODS = ['GET', 'HEAD', 'OPTIONS']


class SubscriptionRequiredMiddleware(MiddlewareMixin):
    """Block write operations for users without an active subscription."""

    EXEMPT_PATHS = EXEMPT_PATHS
    ALWAYS_EXEMPT_ENDPOINTS = ALWAYS_EXEMPT_ENDPOINTS
    EXEMPT_METHODS = EXEMPT_METHODS

    def process_request(self, request):
        if not request.user or isinstance(request.user, AnonymousUser):
            return None

        try:
            from django.utils import timezone

            from api.models.subscription import SubscriptionPlan

            active = SubscriptionPlan.objects.filter(
                user=request.user,
                status='active',
                end_date__gt=timezone.now(),
            ).first()

            if not active and request.method not in self.EXEMPT_METHODS:
                if request.path.startswith('/api/'):
                    return Response(
                        {
                            'error': 'Subscription required',
                            'message': 'You need an active subscription to perform this action',
                            'code': 'SUBSCRIPTION_REQUIRED',
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
        except Exception:
            # Never let a subscription lookup failure break the request.
            import logging

            logging.getLogger(__name__).exception('Subscription check failed')

        return None
