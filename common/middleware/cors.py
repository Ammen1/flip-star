"""
CORS middleware.

Moved from ``api/middleware.py``, where it was registered as
``CustomCorsMiddleware``. It runs ahead of everything else so a preflight
can be answered without touching the database.

Previously (audit finding M-10) this answered *any* origin, known or not,
with ``Access-Control-Allow-Origin: *`` while also sending
``Access-Control-Allow-Credentials: true``. Browsers reject that exact
pairing outright, but where a client doesn't enforce it -- a non-browser
HTTP client, for instance -- it amounts to a credentialed cross-origin
allowlist of "everyone." Fixed here: an origin not in
``settings.CORS_ALLOWED_ORIGINS`` gets no CORS headers at all, which is the
correct behaviour (the browser blocks the cross-origin response, same as if
CORS were never configured for it). Trusted origins are unaffected.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin

ALLOW_METHODS = 'GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD'
ALLOW_HEADERS = (
    'accept, accept-encoding, authorization, content-type, dnt, origin, '
    'user-agent, x-csrftoken, x-requested-with, x-forwarded-for, '
    'x-forwarded-host, x-forwarded-proto'
)
EXPOSE_HEADERS = 'content-type, x-csrftoken'
MAX_AGE = '86400'


def _allowed_origins() -> list[str]:
    return list(getattr(settings, 'CORS_ALLOWED_ORIGINS', []))


def _is_allowed_origin(origin: str) -> bool:
    return bool(origin) and origin in _allowed_origins()


def _apply_headers(response, origin: str) -> None:
    if not _is_allowed_origin(origin):
        # Unknown origin: omit CORS headers entirely rather than falling
        # back to a wildcard. Never pair a wildcard with credentials=true.
        return
    response['Access-Control-Allow-Origin'] = origin
    response['Vary'] = 'Origin'
    response['Access-Control-Allow-Methods'] = ALLOW_METHODS
    response['Access-Control-Allow-Headers'] = ALLOW_HEADERS
    response['Access-Control-Allow-Credentials'] = 'true'
    response['Access-Control-Expose-Headers'] = EXPOSE_HEADERS


class PermissiveCorsMiddleware(MiddlewareMixin):
    """Answer preflights early and attach CORS headers to every response."""

    def process_request(self, request):
        # Short-circuit OPTIONS so a preflight never opens a DB connection.
        if request.method == 'OPTIONS':
            origin = request.META.get('HTTP_ORIGIN', '')
            response = HttpResponse()
            _apply_headers(response, origin)
            if _is_allowed_origin(origin):
                response['Access-Control-Max-Age'] = MAX_AGE
            return response
        return None

    def process_response(self, request, response):
        origin = request.META.get('HTTP_ORIGIN', '')
        _apply_headers(response, origin)

        if request.method == 'OPTIONS':
            response.status_code = 200
            if _is_allowed_origin(origin):
                response['Access-Control-Max-Age'] = MAX_AGE

        return response
