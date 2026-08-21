"""
Security middleware.

Ported from a security assessment done on the ``master`` branch (findings
#11, #13, #14, and the unnumbered scanner-probe/admin-login-throttle work)
that never made it to this branch. Adapted, not copied verbatim:

* Token resolution goes through :class:`common.authentication.ExpiringTokenAuthentication`
  instead of a raw, TTL-unaware ``Token.objects.get()`` -- an admin request
  with an expired token is now rejected consistently whether the block
  happens here or later in DRF's own auth chain.
* Client IP comes from :func:`common.security.get_client_ip`, which only
  trusts ``X-Forwarded-For`` from a configured proxy (see
  ``common/security/client_ip.py``), not the raw header.
* ``print()`` debug statements became ``logger.debug()``.
* Security-event logging goes through the standard ``logging`` module AND
  (as of the ``SecurityEvent`` model landing) a durable, queryable
  ``SecurityEvent`` row per ``logger.warning(...)`` call below -- the
  logging call stays even where the DB write was added, so a log-shipping
  pipeline still sees these in real time without querying the database.

Finding #13's concern (verbose error messages leaking internals) is already
handled by ``common/exceptions/handlers.py`` for every DRF-routed request,
which is broader and more precise than a middleware-level catch-all -- see
that module instead of looking for a ``GenericErrorHandlerMiddleware`` here;
porting one would have been redundant.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils.deprecation import MiddlewareMixin

from common.security import get_client_ip

logger = logging.getLogger(__name__)


def _log_security_event(request, event_type, severity, user, details):
    """Persist a SecurityEvent row alongside the logger.warning() call at
    each site below. Never allowed to break the request it's logging --
    a failure here (e.g. DB unavailable) is itself logged and swallowed."""
    try:
        from api.models.admin import SecurityEvent

        is_authenticated = bool(user and getattr(user, 'is_authenticated', False))
        SecurityEvent.objects.create(
            event_type=event_type,
            severity=severity,
            user=user if is_authenticated else None,
            username=(user.username if is_authenticated else 'Anonymous'),
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            endpoint=request.path,
            action=request.method,
            details=details[:500],
        )
    except Exception:
        logger.exception('Failed to write SecurityEvent row')


class AdminPathGuardMiddleware(MiddlewareMixin):
    """
    Finding #14 -- a single chokepoint guarding every ``/api/admin/*`` path.

    Per-view ``IsAdminUser``-style checks exist on most admin views, but the
    surface is large (dozens of endpoints across many modules) and a single
    missed decorator is a full broken-access-control bug. This middleware
    enforces the same rule at one place: any request under the admin prefix
    must come from an authenticated staff user. Per-view checks remain in
    place as defense in depth, not as the only line of defense.
    """

    ADMIN_PATH_PREFIX = '/api/v1/admin/'

    def process_request(self, request):
        path = request.path or ''
        if not path.startswith(self.ADMIN_PATH_PREFIX):
            return None

        # The CORS middleware answers OPTIONS preflights; let them through.
        if request.method == 'OPTIONS':
            return None

        user = self._resolve_user(request)
        logger.debug(
            'AdminPathGuard: %s %s resolved user=%s staff=%s',
            request.method, path, getattr(user, 'username', None), getattr(user, 'is_staff', False),
        )

        if user is None or not user.is_authenticated:
            logger.warning('AdminPathGuard: blocked unauthenticated request to %s', path)
            _log_security_event(request, 'UNAUTHORIZED_API', 'HIGH', user, 'Authentication required')
            return JsonResponse({'detail': 'Authentication required.'}, status=401)

        if not (getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)):
            logger.warning(
                'AdminPathGuard: blocked non-staff user %s from %s', user.username, path,
            )
            _log_security_event(request, 'UNAUTHORIZED_API', 'HIGH', user, 'Admin privileges required')
            return JsonResponse(
                {'detail': 'You do not have permission to perform this action.'}, status=403,
            )

        # Pin the user so any downstream code that reads request.user (before
        # DRF's own authentication has necessarily run) sees the staff account.
        request.user = user

        # Enforce AdminRole.permission_level for write actions. This is the
        # source of truth even for users whose Django is_superuser flag is
        # True -- the super_admin *role* is independent of the granular
        # *level* (read_only / edit_only / full). Only a user with no
        # AdminRole at all (e.g. a bootstrap `createsuperuser` account)
        # bypasses this -- there is nothing to enforce for them.
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            try:
                from api.models.subscription import AdminRole
                admin_role = AdminRole.objects.filter(user=user, is_active=True).first()
            except Exception:
                admin_role = None

            if admin_role:
                level = admin_role.permission_level
                blocked = level == 'read_only' or (level == 'edit_only' and request.method == 'DELETE')
                if blocked:
                    logger.warning(
                        'AdminPathGuard: blocked %s for %s (role=%s level=%s)',
                        request.method, user.username, admin_role.role, level,
                    )
                    _log_security_event(
                        request, 'PERMISSION_DENIED', 'MEDIUM', user,
                        f'role={admin_role.role} level={level} cannot perform {request.method}',
                    )
                    nice_level = level.replace('_', ' ')
                    return JsonResponse(
                        {
                            'detail': (
                                f'Your access level ({nice_level}) does not allow this action. '
                                'Contact a super admin if you need access.'
                            )
                        },
                        status=403,
                    )
        return None

    @staticmethod
    def _resolve_user(request):
        # Already authenticated upstream (e.g. Django session middleware).
        existing = getattr(request, 'user', None)
        if existing is not None and getattr(existing, 'is_authenticated', False):
            return existing

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header:
            return None
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'token':
            return None

        from common.authentication import ExpiringTokenAuthentication

        try:
            result = ExpiringTokenAuthentication().authenticate_credentials(parts[1])
        except Exception:
            return None
        return result[0] if result else None


class AdminLoginThrottleMiddleware(MiddlewareMixin):
    """Throttle Django's own ``/admin/`` login form: 4 attempts per 10 minutes per client."""

    MAX_ATTEMPTS = 4
    TIME_WINDOW = 600  # seconds

    def _cache_key(self, request) -> str:
        return f'admin_login_attempts:{get_client_ip(request)}'

    def process_request(self, request):
        if not (request.path.startswith('/admin/') and request.method == 'POST'):
            return None

        if cache.get(self._cache_key(request), 0) >= self.MAX_ATTEMPTS:
            return HttpResponse('Too many login attempts. Please try again in 10 minutes.', status=429)
        return None

    def process_response(self, request, response):
        if not (request.path.startswith('/admin/') and request.method == 'POST'):
            return response

        cache_key = self._cache_key(request)
        # Django admin's login view responds 302 on success, 200 (re-rendered
        # form) on failure.
        if response.status_code == 302:
            cache.delete(cache_key)
        elif response.status_code == 200:
            cache.set(cache_key, cache.get(cache_key, 0) + 1, self.TIME_WINDOW)

        return response


class SecurityScanMiddleware(MiddlewareMixin):
    """Block common scanner/bot probe paths, and the root path for obviously automated user agents."""

    BLOCKED_PATHS = (
        '/proc.php', '/nuclei.svg', '/webui', '/admin.php', '/wp-admin',
        '/xmlrpc.php', '/.env', '/config.php', '/phpmyadmin', '/mysql', '/runners',
    )

    SUSPICIOUS_UA_PATTERNS = ('scanner', 'crawler', 'nuclei', 'nikto', 'sqlmap', 'masscan')

    def process_request(self, request):
        path = request.path.lower()

        if path == '/' and self._is_suspicious_user_agent(request):
            logger.warning(
                'SecurityScan: blocked root-path probe from %s (UA=%r)',
                get_client_ip(request), request.META.get('HTTP_USER_AGENT', ''),
            )
            _log_security_event(
                request, 'SCANNER_PROBE', 'LOW', getattr(request, 'user', None),
                'Blocked root path probe from suspicious user agent',
            )
            return HttpResponseForbidden()

        for blocked in self.BLOCKED_PATHS:
            if blocked in path:
                logger.warning(
                    'SecurityScan: blocked scanner probe %s from %s', request.path, get_client_ip(request),
                )
                _log_security_event(
                    request, 'SCANNER_PROBE', 'LOW', getattr(request, 'user', None),
                    f'Blocked scanner probe: {blocked}',
                )
                return HttpResponseForbidden()

        return None

    def _is_suspicious_user_agent(self, request) -> bool:
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        return any(pattern in user_agent for pattern in self.SUSPICIOUS_UA_PATTERNS)


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Response security headers not already covered by Django's own
    ``SecurityMiddleware``. Only ever adds a header that isn't already set,
    so anything set upstream (nginx, another middleware) wins.
    """

    _CSP_TEMPLATE = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:{extra}; "
        "media-src 'self' blob: https:{extra}; "
        "font-src 'self' data: https:; "
        "connect-src 'self' https: wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'"
    )

    def _csp(self) -> str:
        # The media/storage domain is configured, not hardcoded -- unlike
        # the reference this was ported from, which hardcoded one specific
        # deployment's S3-compatible endpoint directly into the policy.
        domain = (getattr(settings, 'S3_CUSTOM_DOMAIN', '') or '').strip()
        extra = f' {domain}' if domain else ''
        return self._CSP_TEMPLATE.format(extra=extra)

    def process_response(self, request, response):
        response.setdefault('Content-Security-Policy', self._csp())
        response.setdefault('X-Content-Type-Options', 'nosniff')
        response.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        return response
