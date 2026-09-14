"""
Per-endpoint throttle classes and failure-counting helpers.

There is currently no rate limiting anywhere in the API: ``REST_FRAMEWORK``
has no ``DEFAULT_THROTTLE_CLASSES``, so login, OTP, and password-reset
endpoints accept unlimited attempts. This adds scoped throttles for those
endpoints, bound to rates in ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']``.

Two things matter beyond "add throttling":

* **Identity, not IP.** Throttling by IP alone is bypassed by anyone who
  changes IP (mobile networks do this naturally; an attacker does it on
  purpose). These throttle by account identifier first -- the authenticated
  user, or a username/email/phone taken from the request body for anonymous
  auth attempts -- and only fall back to IP when no such identifier exists.
  A malicious ``X-Forwarded-For`` cannot make this resolve to a different
  account than the one actually being attacked.
* **The IP fallback itself must not trust a spoofable header.** When IP
  *is* the identifier (truly anonymous requests with nothing else to key
  on), it comes from ``common.security.get_client_ip``, which only honours
  ``X-Forwarded-For`` from a configured trusted proxy -- see
  ``common/security/client_ip.py``.
"""

from __future__ import annotations

import re

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from common.security.client_ip import get_client_ip

_RATE_RE = re.compile(r'^\s*(\d+)\s*/\s*(\d*)\s*([smhd])[a-z]*\s*$', re.IGNORECASE)


class _ExtendedRateMixin:
    """
    DRF's default ``parse_rate`` only handles single-unit periods like
    ``3/m``, ``5/h`` -- it inspects ``period[0]`` only, so ``3/10min``
    raises ``KeyError``. This extends the parser to accept a leading
    multiplier on the period (``3/10min``, ``5/30s``, ``10/2h``), falling
    back to DRF's parser for anything it doesn't recognise.
    """

    def parse_rate(self, rate):
        if rate is None:
            return (None, None)
        m = _RATE_RE.match(rate)
        if not m:
            return super().parse_rate(rate)
        num_requests = int(m.group(1))
        multiplier = int(m.group(2)) if m.group(2) else 1
        unit = m.group(3).lower()
        unit_seconds = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit]
        return (num_requests, unit_seconds * multiplier)

    def get_ident(self, request):
        return _get_throttle_ident(request)


class _ExtendedAnonThrottle(_ExtendedRateMixin, AnonRateThrottle):
    pass


class _ExtendedUserThrottle(_ExtendedRateMixin, UserRateThrottle):
    pass


def _make(scope_name: str):
    """Build an (anon, user) pair of throttles bound to the same scope name."""
    anon = type(
        f'{scope_name.title()}AnonThrottle', (_ExtendedAnonThrottle,), {'scope': scope_name}
    )
    user = type(
        f'{scope_name.title()}UserThrottle', (_ExtendedUserThrottle,), {'scope': scope_name}
    )
    return anon, user


LoginAnonThrottle, LoginUserThrottle = _make('login')
OtpSendAnonThrottle, OtpSendUserThrottle = _make('otp_send')
OtpVerifyAnonThrottle, OtpVerifyUserThrottle = _make('otp_verify')
PasswordResetAnonThrottle, PasswordResetUserThrottle = _make('password_reset')
PhoneLookupAnonThrottle, PhoneLookupUserThrottle = _make('phone_lookup')
# Report submission is IsAuthenticated-only, so no anon counterpart is wired up.
_ReportAnonThrottle, ReportUserThrottle = _make('report')
MediaRefreshAnonThrottle, MediaRefreshUserThrottle = _make('media_refresh')


def _get_throttle_ident(request) -> str:
    """
    Account-based identifier for throttling. Priority: authenticated user >
    username/email/phone from the request body > IP address (last resort,
    and only via the trusted-proxy-aware resolver).
    """
    if getattr(request, 'user', None) and request.user.is_authenticated:
        return f'user_{request.user.id}'

    data = getattr(request, 'data', None)
    if data:
        for field in ('username', 'email', 'phone'):
            value = (data.get(field) or '').strip() if hasattr(data, 'get') else ''
            if value:
                return f'{field}_{value}'

    return f'ip_{get_client_ip(request)}'


def reset_throttle(request, scope: str) -> None:
    """
    Reset the DRF throttle counter for ``scope``/this request's identifier.
    Call on successful login/password-reset so a legitimate success doesn't
    count against the rate limit.
    """
    from django.core.cache import cache

    ident = _get_throttle_ident(request)
    # Matches DRF's SimpleRateThrottle cache key format exactly.
    cache.delete(f'throttle_{scope}_{ident}')


def check_and_increment_failure(request, scope: str, max_attempts: int, window_seconds: int) -> int:
    """
    Manually count a failed attempt (not a DRF throttle -- a separate
    counter for endpoints that must only count *failures*, e.g. login should
    not lock someone out after N successful requests). Returns attempts
    remaining before the next request is blocked (0 means just-blocked).
    """
    from django.core.cache import cache

    ident = _get_throttle_ident(request)
    cache_key = f'failed_attempts_{scope}_{ident}'

    attempts = cache.get(cache_key, 0) + 1
    cache.set(cache_key, attempts, window_seconds)
    return max(0, max_attempts - attempts)


def is_blocked(request, scope: str, max_attempts: int) -> bool:
    """Check whether this identifier is currently blocked, without incrementing."""
    from django.core.cache import cache

    ident = _get_throttle_ident(request)
    cache_key = f'failed_attempts_{scope}_{ident}'
    return cache.get(cache_key, 0) >= max_attempts


def clear_failures(request, scope: str) -> None:
    """Clear the failed-attempt counter, e.g. on successful login."""
    from django.core.cache import cache

    ident = _get_throttle_ident(request)
    cache_key = f'failed_attempts_{scope}_{ident}'
    cache.delete(cache_key)
