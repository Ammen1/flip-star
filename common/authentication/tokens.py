"""
Expiring token authentication.

DRF's ``TokenAuthentication`` issues tokens that never expire. Combined with
no session invalidation on password change, a stolen or leaked token stays
valid forever. This wraps it with a TTL check: a token older than
``settings.AUTH_TOKEN_TTL_DAYS`` is deleted server-side and the request is
rejected with a 401, forcing the client to re-authenticate.

This project has exactly one token type -- ``rest_framework.authtoken.models.Token``,
issued via ``Token.objects.get_or_create(user=user)`` on every login -- no
refresh token, no JWT, nothing else to keep in sync. ``get_or_create`` means
login normally *reuses* the same token rather than rotating it, so this TTL
is the only expiry mechanism in the system: once this class deletes an
expired token, the next successful login's ``get_or_create`` finds no
existing row and issues a fresh one automatically. No login call site needs
to change for that to work.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ExpiringTokenAuthentication(TokenAuthentication):
    """``TokenAuthentication`` that rejects tokens older than ``AUTH_TOKEN_TTL_DAYS``. """

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)

        ttl_days = getattr(settings, 'AUTH_TOKEN_TTL_DAYS', 14)
        if ttl_days and ttl_days > 0:
            age = timezone.now() - token.created
            if age > timedelta(days=ttl_days):
                token.delete()
                raise AuthenticationFailed(
                    'Authentication token has expired. Please log in again.'
                )

        return user, token
