"""
Request-scoped logging context and redaction.

Provides the pieces referenced by :func:`common.constants.logging.build_logging_config`:

* :class:`RequestContextMiddleware` -- assigns a request ID and records the
  authenticated user for the duration of the request.
* :class:`RequestContextFilter` -- injects that context onto every log record so
  a single request can be traced across modules.
* :class:`SensitiveDataFilter` -- redacts credentials and one-time codes.
* :class:`JsonFormatter` -- single-line JSON output for log aggregation.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import uuid
from typing import Any

from common.constants.logging import REDACTION, SENSITIVE_MARKERS

#: Correlation identifier for the in-flight request.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default='-')
#: Authenticated user id for the in-flight request, or ``-`` when anonymous.
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('user_id', default='-')

#: Header a load balancer may use to supply an upstream correlation id.
REQUEST_ID_HEADER = 'HTTP_X_REQUEST_ID'
#: Header echoed back to the client so a user can quote it in a bug report.
RESPONSE_HEADER = 'X-Request-ID'

# key=value / "key": "value" pairs whose value must be scrubbed.
_KV_PATTERN = re.compile(
    r'(?i)\b(' + '|'.join(SENSITIVE_MARKERS) + r')(["\']?\s*[:=]\s*["\']?)([^\s,;"\'})\]]+)'
)


class RequestContextMiddleware:
    """Assign a correlation id to each request and expose it on the response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get(REQUEST_ID_HEADER)
        request_id = incoming or uuid.uuid4().hex[:16]

        token_request = request_id_var.set(request_id)
        token_user = user_id_var.set('-')

        request.request_id = request_id
        try:
            response = self.get_response(request)

            user = getattr(request, 'user', None)
            if user is not None and getattr(user, 'is_authenticated', False):
                user_id_var.set(str(user.pk))

            response[RESPONSE_HEADER] = request_id
            return response
        finally:
            request_id_var.reset(token_request)
            user_id_var.reset(token_user)


class RequestContextFilter(logging.Filter):
    """Attach ``request_id`` and ``user_id`` to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        return True


class SensitiveDataFilter(logging.Filter):
    """
    Redact credentials and one-time codes from log records.

    This is a safety net, not a licence to log secrets. The correct fix is to
    never pass them to a logger in the first place.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True

        redacted = _KV_PATTERN.sub(lambda m: f'{m.group(1)}{m.group(2)}{REDACTION}', message)

        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            'timestamp': self.formatTime(record, '%Y-%m-%dT%H:%M:%S'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'request_id': getattr(record, 'request_id', '-'),
            'user_id': getattr(record, 'user_id', '-'),
        }

        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)

        for key in ('transaction_id', 'operation', 'duration_ms', 'provider', 'result'):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        return json.dumps(payload, default=str)
