"""
Centralised DRF exception handling.

Deliberately contract-preserving. The response *body* produced for every
exception DRF already knew how to handle is byte-for-byte what it was before
this module existed, because 242 endpoints are consumed by a released mobile
application and changing the error envelope would break it.

What this handler adds:

* structured logging of every failure, correlated by request id;
* translation of :class:`~common.exceptions.base.DomainError` into the same
  ``{"error": ...}`` shape the existing function-based views already return;
* a guarantee that an unexpected exception never returns a traceback to the
  client (audit finding H-19).

Standardising the success/error envelope across all endpoints is a separate,
breaking change and is documented in ``docs/api.md`` rather than done here.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from common.exceptions.base import DomainError

logger = logging.getLogger(__name__)


def _describe(context: dict[str, Any]) -> dict[str, Any]:
    request = context.get('request')
    view = context.get('view')
    return {
        'path': getattr(request, 'path', '-'),
        'method': getattr(request, 'method', '-'),
        'view': type(view).__name__ if view else '-',
    }


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """
    DRF ``EXCEPTION_HANDLER``.

    Returning ``None`` hands the exception back to Django, which produces the
    standard 500. That path is preserved so behaviour under ``DEBUG`` is
    unchanged for developers.
    """
    detail = _describe(context)

    # Business-rule failures: expected, logged at warning, mapped to the shape
    # the existing views already emit.
    if isinstance(exc, DomainError):
        logger.warning(
            'Domain error: %s',
            exc.message,
            extra={'operation': detail['view'], 'result': exc.code},
        )
        return Response(exc.to_dict(), status=exc.status_code)

    response = drf_exception_handler(exc, context)

    if response is not None:
        # DRF handled it (validation, auth, permission, 404, throttling).
        # Body is returned untouched.
        logger.info(
            'API error %s on %s %s',
            response.status_code,
            detail['method'],
            detail['path'],
            extra={'operation': detail['view'], 'result': response.status_code},
        )
        return response

    # Unhandled: log the full traceback server-side, expose nothing.
    logger.exception(
        'Unhandled exception on %s %s',
        detail['method'],
        detail['path'],
        extra={'operation': detail['view'], 'result': 'unhandled'},
    )

    if settings.DEBUG:
        # Let Django render its debug page for developers.
        return None

    return Response(
        {'error': 'An internal error occurred.', 'code': 'internal_error'},
        status=500,
    )
