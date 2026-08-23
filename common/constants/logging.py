"""
Logging configuration.

Replaces the 483 ``print()`` calls the codebase used for diagnostics (audit
finding H-15). Production emits single-line JSON suitable for shipping to a log
aggregator; development emits readable text.

Every record passes through :class:`~common.middleware.logging.SensitiveDataFilter`,
which redacts OTP codes, tokens, passwords and API credentials.
"""

from __future__ import annotations

from typing import Any

#: Substrings that mark a log record as containing material that must never be
#: persisted. Matched case-insensitively against the formatted message.
SENSITIVE_MARKERS = (
    'password',
    'otp',
    'token',
    'secret',
    'credential',
    'api_key',
    'application_key',
    'private_key',
    'authorization',
)

#: Replacement written in place of a redacted value.
REDACTION = '[REDACTED]'


def build_logging_config(level: str = 'INFO', json_format: bool = False) -> dict[str, Any]:
    """
    Build a ``LOGGING`` dict.

    Args:
        level: Root log level for application loggers.
        json_format: Emit structured JSON instead of human-readable text.
    """
    level = level.upper()

    formatter = 'json' if json_format else 'verbose'

    return {
        'version': 1,
        'disable_existing_loggers': False,
        'filters': {
            'redact_sensitive': {
                '()': 'common.middleware.logging.SensitiveDataFilter',
            },
            'request_context': {
                '()': 'common.middleware.logging.RequestContextFilter',
            },
        },
        'formatters': {
            'verbose': {
                'format': (
                    '%(asctime)s %(levelname)-8s %(name)s '
                    '[req=%(request_id)s user=%(user_id)s] %(message)s'
                ),
            },
            'json': {
                '()': 'common.middleware.logging.JsonFormatter',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': formatter,
                'filters': ['request_context', 'redact_sensitive'],
            },
        },
        'root': {
            'handlers': ['console'],
            'level': level,
        },
        'loggers': {
            'django': {
                'handlers': ['console'],
                'level': level,
                'propagate': False,
            },
            'django.db.backends': {
                # Query logging is extremely noisy and leaks data; opt in only.
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False,
            },
            'daphne.http_protocol': {
                # Four lines per request (open, response started, close,
                # complete) with no information the access log doesn't already
                # carry. The kubelet probes /api/v1/health/ for liveness and
                # readiness every ten seconds, so at DEBUG this alone produces
                # roughly 40,000 lines a day and buries everything else in the
                # pod logs. Pinned rather than left to LOG_LEVEL so staging can
                # keep DEBUG for application loggers, which is the point of
                # running staging at DEBUG at all.
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False,
            },
            'api': {
                'handlers': ['console'],
                'level': level,
                'propagate': False,
            },
            'celery': {
                'handlers': ['console'],
                'level': level,
                'propagate': False,
            },
        },
    }
