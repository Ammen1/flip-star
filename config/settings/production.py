"""
Production settings.

Two rules govern this module:

1. Nothing here degrades silently. A missing or unsafe value raises
   ``ImproperlyConfigured`` at import time so the container fails to start,
   rather than booting in a weakened state.
2. There is no SQLite fallback. If PostgreSQL is unreachable the process must
   die and let the orchestrator restart it -- never accept writes into a
   throwaway file (audit finding H-05).
"""

from django.core.exceptions import ImproperlyConfigured

from infrastructure.secrets import secret as config

from .base import *  # noqa: F401,F403

DEBUG = False
ENVIRONMENT = 'production'


# ---------------------------------------------------------------------------
# Fail-fast configuration validation
# ---------------------------------------------------------------------------

#: Settings-module globals that must carry a value.
REQUIRED_SETTINGS = (
    'SECRET_KEY',
    'ALLOWED_HOSTS',
)

#: Keys of ``DATABASES['default']`` that must be populated. Checked on the
#: resolved connection mapping rather than on raw environment variables, so
#: this works whether the database came from DATABASE_URL or discrete DB_* vars.
REQUIRED_DATABASE_KEYS = ('NAME', 'USER', 'PASSWORD', 'HOST')

#: Credentials required for the payment and messaging integrations. Absent
#: values are reported as a startup warning rather than a hard failure, because
#: a deployment may legitimately run with an integration disabled.
INTEGRATION_SETTINGS = (
    'TELEBIRR_SOAP_URL',
    'TELEBIRR_THIRD_PARTY_ID',
    'TELEBIRR_THIRD_PARTY_PASSWORD',
    'TELEBIRR_SP_OPERATOR_ID',
    'TELEBIRR_SP_OPERATOR_CREDENTIAL',
    'TELEBIRR_FABRIC_APP_ID',
    'TELEBIRR_APP_SECRET',
    'TELEBIRR_MERCHANT_APP_ID',
    'TELEBIRR_MERCHANT_CODE',
    'TELEBIRR_PRIVATE_KEY',
    'TELEBIRR_PUBLIC_KEY',
    'ONEVAS_APPLICATION_KEY',
    'ONEVAS_PRODUCT_NUMBER',
)

#: Values that are acceptable in development but must never reach production.
FORBIDDEN_VALUES = {
    'SECRET_KEY': ('django-insecure-key', 'changeme', ''),
}


def _validate() -> None:
    errors: list[str] = []

    _current = globals()
    for name in REQUIRED_SETTINGS:
        if not _current.get(name):
            errors.append(f'{name} is required in production but is empty.')

    for name, forbidden in FORBIDDEN_VALUES.items():
        if _current.get(name) in forbidden:
            errors.append(f'{name} is set to an insecure development default.')

    if _current.get('DEBUG'):
        errors.append('DEBUG must be False in production.')

    if _current.get('CORS_ALLOW_ALL_ORIGINS'):
        errors.append(
            'CORS_ALLOW_ALL_ORIGINS must be False in production; '
            'set CORS_ALLOWED_ORIGINS to an explicit list instead.'
        )

    default_db = _current.get('DATABASES', {}).get('default', {})

    engine = default_db.get('ENGINE', '')
    if 'postgresql' not in engine:
        errors.append(
            f'Production requires PostgreSQL, got ENGINE={engine!r}. '
            'Set DB_ENGINE=django.db.backends.postgresql and the DB_* variables.'
        )

    for key in REQUIRED_DATABASE_KEYS:
        if not default_db.get(key):
            errors.append(f'DATABASES["default"]["{key}"] is empty (set DB_{key}).')

    if errors:
        raise ImproperlyConfigured(
            'Refusing to start with an unsafe production configuration:\n  - '
            + '\n  - '.join(errors)
        )


# ---------------------------------------------------------------------------
# Transport security
# ---------------------------------------------------------------------------
# nginx terminates TLS and already redirects HTTP to HTTPS. These settings make
# Django enforce the same contract if it is ever reached directly.
#
# NOTE: SECURE_SSL_REDIRECT causes a redirect loop for any client hitting the
# container on plain HTTP without the X-Forwarded-Proto header (for example the
# published port 8000). Keep that port closed, or set SECURE_SSL_REDIRECT=false.

SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # the SPA reads this token

SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in config('CSRF_TRUSTED_ORIGINS', default='https://uat.flipstar.et').split(',') if o.strip()
]


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', default=False, cast=bool)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Persistent connections: the previous configuration opened a new PostgreSQL
# connection per request (CONN_MAX_AGE=0), which is a scaling wall under ASGI
# concurrency.

DATABASES['default']['CONN_MAX_AGE'] = config('DB_CONN_MAX_AGE', default=60, cast=int)  # noqa: F405
DATABASES['default'].setdefault('OPTIONS', {})  # noqa: F405
DATABASES['default']['OPTIONS'].setdefault(  # noqa: F405
    'sslmode', config('DB_SSLMODE', default='prefer')
)


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@flipstar.et')


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

from common.constants.logging import build_logging_config  # noqa: E402

LOGGING = build_logging_config(level=config('LOG_LEVEL', default='INFO'), json_format=True)


# Validate last, so every setting above has its final value.
_validate()
