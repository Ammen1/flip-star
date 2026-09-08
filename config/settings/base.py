"""
Base Django settings shared by every environment.

Environment-specific modules (``development``, ``production``, ``testing``)
import from here and override only what differs. Nothing in this module may
assume it is running in a particular environment.

Select the active module with ``DJANGO_SETTINGS_MODULE``, e.g.::

    DJANGO_SETTINGS_MODULE=config.settings.production

``config.settings`` (the package itself) remains importable for backward
compatibility and dispatches on ``DJANGO_ENV`` -- see ``__init__.py``.
"""

import mimetypes
import os
from pathlib import Path

from infrastructure.secrets import secret as config

# backend/config/settings/base.py -> backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

SECRET_KEY = config('SECRET_KEY', default='django-insecure-key')
DEBUG = config('DEBUG', default=False, cast=bool)

# Hosts that must always resolve regardless of what the environment supplies:
# the loopback names used by health checks and the Docker network.
REQUIRED_HOSTS = ['localhost', '127.0.0.1']

ALLOWED_HOSTS = [
    h.strip()
    for h in config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')
    if h.strip()
]
for _host in REQUIRED_HOSTS:
    if _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'channels',
    'django_celery_beat',
]

LOCAL_APPS = [
    'api',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

MIDDLEWARE = [
    'common.middleware.cors.PermissiveCorsMiddleware',
    'common.middleware.security.SecurityScanMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # Assigns the request-id/user-id context every log line carries. Built
    # during the restructure but never actually registered here -- fixed
    # incidentally while touching this list for the items above/below.
    'common.middleware.logging.RequestContextMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Runs after AuthenticationMiddleware so request.user is populated;
    # resolves a DRF token from the header itself otherwise.
    'common.middleware.security.AdminPathGuardMiddleware',
    'common.middleware.security.AdminLoginThrottleMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'common.middleware.security.SecurityHeadersMiddleware',
]


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'api', 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Built by ``infrastructure.database.config`` so the same resolution logic is
# testable and shared. Environment modules may override DATABASES entirely.

from infrastructure.database.config import build_database_config  # noqa: E402

DATABASES = {'default': build_database_config(BASE_DIR)}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'common.authentication.ExpiringTokenAuthentication',
    ],
    # NOTE: this remains AllowAny to preserve current behaviour. Tightening it
    # to IsAuthenticated is tracked as audit finding C-10 and requires an
    # endpoint-by-endpoint review before it can be flipped safely.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'EXCEPTION_HANDLER': 'common.exceptions.handlers.api_exception_handler',
    # Not globally enforced (no DEFAULT_THROTTLE_CLASSES) -- these are scopes
    # for views that opt in via @throttle_classes(...). See
    # common/throttling.py for the throttle classes themselves and the
    # account-based (not IP-based) identifier they key on.
    'DEFAULT_THROTTLE_RATES': {
        'login': '6/10min',
        'otp_send': '5/min',
        'otp_verify': '10/min',
        'password_reset': '5/min',
        'phone_lookup': '20/min',
        'report': '5/hour',
    },
}

# How long an auth token stays valid after creation, in days. A token older
# than this is deleted and the request rejected with 401, forcing
# re-authentication -- closes the "stolen token is valid forever" gap DRF's
# TokenAuthentication otherwise leaves open. See common/authentication/tokens.py.
AUTH_TOKEN_TTL_DAYS = config('AUTH_TOKEN_TTL_DAYS', default=14, cast=int)

# IPs/CIDR ranges allowed to set X-Forwarded-For and have it trusted for
# rate-limit/audit-log purposes. Defaults to loopback, correct when nginx (or
# another reverse proxy) runs on the same host/Docker network as this
# process. A request whose direct peer is NOT in this list has its
# X-Forwarded-For header ignored entirely -- see common/security/client_ip.py.
TRUSTED_PROXY_IPS = [
    ip.strip()
    for ip in config('TRUSTED_PROXY_IPS', default='127.0.0.1,::1').split(',')
    if ip.strip()
]


# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Addis_Ababa'
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Absolute base used by serializers when building media URLs in API responses.
BACKEND_URL = config('BACKEND_URL', default='https://api.uat.flipstar.et')

# Object storage (S3 / MinIO). Resolved centrally so the same values are used
# by Django's storage backend and by the Celery upload helpers.
from infrastructure.storage.config import apply_storage_settings  # noqa: E402

_storage = apply_storage_settings(media_url=MEDIA_URL)
S3_ACCESS_KEY_ID = _storage['access_key_id']
S3_SECRET_ACCESS_KEY = _storage['secret_access_key']
S3_BUCKET_NAME = _storage['bucket_name']
S3_REGION_NAME = _storage['region_name']
S3_ENDPOINT_URL = _storage['endpoint_url']
S3_CUSTOM_DOMAIN = _storage['custom_domain']
DEFAULT_FILE_STORAGE = _storage['default_file_storage']
STATICFILES_STORAGE = _storage['staticfiles_storage']
MEDIA_URL = _storage['media_url']

# django-storages reads AWS_STORAGE_BUCKET_NAME to find the bucket.
AWS_STORAGE_BUCKET_NAME = _storage['bucket_name']
if _storage['access_key_id']:
    AWS_ACCESS_KEY_ID = _storage['access_key_id']
if _storage['secret_access_key']:
    AWS_SECRET_ACCESS_KEY = _storage['secret_access_key']
if _storage['region_name']:
    AWS_S3_REGION_NAME = _storage['region_name']
if _storage['endpoint_url']:
    AWS_S3_ENDPOINT_URL = _storage['endpoint_url']
    AWS_S3_USE_SSL = _storage['use_ssl']
if _storage['default_acl']:
    AWS_DEFAULT_ACL = _storage['default_acl']

# Stable, cacheable media URLs. See infrastructure/storage/config.py: presigned
# URLs rotate their signature on every call, so the same object arrives under a
# new URL in every API response and no browser or CDN cache can ever hit.
AWS_QUERYSTRING_AUTH = _storage['querystring_auth']
AWS_S3_OBJECT_PARAMETERS = _storage['object_parameters']

# Video MIME types must be registered for range-request streaming to work.
mimetypes.add_type('video/mp4', '.mp4', True)
mimetypes.add_type('video/webm', '.webm', True)
mimetypes.add_type('video/ogg', '.ogv', True)

STREAMING_CONTENT_LENGTH = 4096

FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# Redis-backed services: cache, channel layer, Celery
# ---------------------------------------------------------------------------

REDIS_HOST = config('REDIS_HOST', default='127.0.0.1')
REDIS_PORT = int(config('REDIS_PORT', default=6379))
REDIS_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}'

# OTP codes, rate-limit counters and throttle state live in the cache. It must
# be shared across processes -- see audit finding H-02.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': f'{REDIS_URL}/1',
    }
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {'hosts': [(REDIS_HOST, REDIS_PORT)]},
    },
}

# Separate logical DB from the cache (1) and Celery broker (0), so that an
# operational cache flush (`cache.clear()`, `redis-cli -n 1 FLUSHDB`) can
# never take the application's identity keypair down with it. See
# infrastructure/keys/.
REDIS_CRYPTO_URL = f'{REDIS_URL}/2'

CELERY_BROKER_URL = f'{REDIS_URL}/0'
CELERY_RESULT_BACKEND = f'{REDIS_URL}/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in config(
        'CORS_ALLOWED_ORIGINS',
        default='https://api.uat.flipstar.et,http://localhost:3000,http://localhost:5173,http://localhost:5174',
    ).split(',')
    if o.strip()
]

CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', default=True, cast=bool)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-forwarded-for',
    'x-forwarded-host',
    'x-forwarded-proto',
    'x-client-public-key',
]
CORS_EXPOSE_HEADERS = ['content-type', 'x-csrftoken']


# ---------------------------------------------------------------------------
# Proxy
# ---------------------------------------------------------------------------

# nginx terminates TLS and forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# ---------------------------------------------------------------------------
# Third-party integrations
# ---------------------------------------------------------------------------
# No credential below carries a usable default. A missing value yields an empty
# string, and ``production.py`` refuses to start when a required one is blank.
# Previous versions shipped live Telebirr and Onevas credentials as defaults.

# Web Push (VAPID). Generate with: python -m py_vapid --gen --applicationServerKey
VAPID_PUBLIC_KEY = config('VAPID_PUBLIC_KEY', default='')
VAPID_PRIVATE_KEY = config('VAPID_PRIVATE_KEY', default='')
VAPID_SUBJECT = config('VAPID_SUBJECT', default='mailto:admin@flipstar.et')

# Telebirr Direct Debit (SOAP)
TELEBIRR_SOAP_URL = config('TELEBIRR_SOAP_URL', default='')
TELEBIRR_THIRD_PARTY_ID = config('TELEBIRR_THIRD_PARTY_ID', default='')
TELEBIRR_THIRD_PARTY_PASSWORD = config('TELEBIRR_THIRD_PARTY_PASSWORD', default='')
TELEBIRR_SHORTCODE = config('TELEBIRR_SHORTCODE', default='')
TELEBIRR_RESULT_URL = config('TELEBIRR_RESULT_URL', default='')

# ---------------------------------------------------------------------------
# Crypto test endpoints -- DEVELOPMENT AND STAGING ONLY
# ---------------------------------------------------------------------------
# When true, /api/v1/crypto/test/* is served: helpers that generate a client
# keypair, encrypt an arbitrary payload, and decrypt a response. They exist so
# the encrypted endpoints can be exercised from Postman or curl without a
# crypto-capable client.
#
# This MUST be false in production. The helpers hand out a private key and
# perform the client half of the exchange server-side, which removes the
# end-to-end property the encryption exists to provide: an attacker who can
# reach them can mint valid envelopes for any payload. Gated on its own flag
# rather than DEBUG because staging runs config.settings.production with
# DEBUG=False, and staging is precisely where these need to work.
#
# When false the routes return 404, not 403 -- a disabled endpoint should not
# advertise that it exists.
CRYPTO_TEST_ENDPOINTS_ENABLED = config('CRYPTO_TEST_ENDPOINTS_ENABLED', default=False, cast=bool)
TELEBIRR_PAYEE_ACCOUNT_NAME = config('TELEBIRR_PAYEE_ACCOUNT_NAME', default='Flipstar')
TELEBIRR_CALLER_TYPE = config('TELEBIRR_CALLER_TYPE', default='2')
TELEBIRR_SP_OPERATOR_ID = config('TELEBIRR_SP_OPERATOR_ID', default='')
TELEBIRR_SP_OPERATOR_CREDENTIAL = config('TELEBIRR_SP_OPERATOR_CREDENTIAL', default='')
TELEBIRR_ORG_OPERATOR_ID = config('TELEBIRR_ORG_OPERATOR_ID', default='')
TELEBIRR_ORG_OPERATOR_CREDENTIAL = config('TELEBIRR_ORG_OPERATOR_CREDENTIAL', default='')

# Telebirr B2C (Business-to-Consumer payouts, e.g. withdrawal payouts).
# Falls back to the direct-debit org-operator/third-party credentials above
# when unset -- see TelebirrDirectDebitService.initiate_b2c_payment.
TELEBIRR_B2C_SERVICE_CODE = config('TELEBIRR_B2C_SERVICE_CODE', default='2304')
TELEBIRR_B2C_REASON_TYPE = config(
    'TELEBIRR_B2C_REASON_TYPE', default='Pay for Individual B2C_VDF_Demo'
)
TELEBIRR_B2C_RESULT_URL = config('TELEBIRR_B2C_RESULT_URL', default='')
TELEBIRR_B2C_ORG_OPERATOR_ID = config('TELEBIRR_B2C_ORG_OPERATOR_ID', default='')
TELEBIRR_B2C_ORG_OPERATOR_CREDENTIAL = config('TELEBIRR_B2C_ORG_OPERATOR_CREDENTIAL', default='')
TELEBIRR_B2C_SOAP_URL = config('TELEBIRR_B2C_SOAP_URL', default='')
TELEBIRR_B2C_THIRD_PARTY_ID = config('TELEBIRR_B2C_THIRD_PARTY_ID', default='')
TELEBIRR_B2C_THIRD_PARTY_PASSWORD = config('TELEBIRR_B2C_THIRD_PARTY_PASSWORD', default='')

# Telebirr USSD Push (BuyGoodsForCustomer -- an immediate PIN-entry prompt on
# the payer's phone, used for coin purchases and one-time subscription
# payments). Falls back to the direct-debit settings above when unset -- see
# TelebirrDirectDebitService.initiate_ussd_push_payment.
TELEBIRR_USSD_MERCHANT_SHORTCODE = config('TELEBIRR_USSD_MERCHANT_SHORTCODE', default='')
TELEBIRR_USSD_RESULT_URL = config('TELEBIRR_USSD_RESULT_URL', default='')
TELEBIRR_USSD_SOAP_URL = config('TELEBIRR_USSD_SOAP_URL', default='')
TELEBIRR_USSD_THIRD_PARTY_ID = config('TELEBIRR_USSD_THIRD_PARTY_ID', default='')
TELEBIRR_USSD_THIRD_PARTY_PASSWORD = config('TELEBIRR_USSD_THIRD_PARTY_PASSWORD', default='')
TELEBIRR_USSD_ORG_OPERATOR_ID = config('TELEBIRR_USSD_ORG_OPERATOR_ID', default='')
TELEBIRR_USSD_ORG_OPERATOR_CREDENTIAL = config('TELEBIRR_USSD_ORG_OPERATOR_CREDENTIAL', default='')
# Separate webhook URL for the subscription-specific USSD Push flow below,
# distinct from the general coin-purchase one above.
TELEBIRR_SUBSCRIPTION_USSD_RESULT_URL = config('TELEBIRR_SUBSCRIPTION_USSD_RESULT_URL', default='')

# Ethio Telecom CRM (PresentServiceGift API -- data-gift awards distinct
# from Telebirr B2C cash payouts above). Used by api/services/crm_service.py.
CRM_ENDPOINT = config('CRM_ENDPOINT', default='')
CRM_SERVICE_NUMBER_A = config('CRM_SERVICE_NUMBER_A', default='')
CRM_ACCESS_USER = config('CRM_ACCESS_USER', default='')
CRM_ACCESS_PASSWORD = config('CRM_ACCESS_PASSWORD', default='')
CRM_CHANNEL_ID = config('CRM_CHANNEL_ID', default='')
CRM_TECHNICAL_CHANNEL_ID = config('CRM_TECHNICAL_CHANNEL_ID', default='')
CRM_TENANT_ID = config('CRM_TENANT_ID', default='')
CRM_CURRENCY_ID = config('CRM_CURRENCY_ID', default='1048')  # ETB currency ID -- not a secret
CRM_CHARGE_CODE = config('CRM_CHARGE_CODE', default='CC_GIFT_ONCE_OFF_FEE')  # not a secret
CRM_OFFERING_ID = config('CRM_OFFERING_ID', default='')

# Telebirr H5 / SuperApp Web Checkout (Fabric Payment Gateway). Used by
# TelebirrService (api/integrations/telebirr/checkout.py) for the H5 InApp
# flow: applyFabricToken -> preOrder -> rawRequest -> js_fun_start_pay ->
# notify/queryOrder. Test bed defaults point at the developer portal.
TELEBIRR_H5_BASE_URL = config(
    'TELEBIRR_H5_BASE_URL',
    default='https://superapp.ethiomobilemoney.et:38443/apiaccess/payment/gateway',
)
TELEBIRR_FABRIC_APP_ID = config('TELEBIRR_FABRIC_APP_ID', default='')
TELEBIRR_APP_SECRET = config('TELEBIRR_APP_SECRET', default='')
TELEBIRR_MERCHANT_APP_ID = config('TELEBIRR_MERCHANT_APP_ID', default='')
TELEBIRR_MERCHANT_CODE = config('TELEBIRR_MERCHANT_CODE', default='')
TELEBIRR_PRIVATE_KEY = config('TELEBIRR_PRIVATE_KEY', default='')
TELEBIRR_PUBLIC_KEY = config('TELEBIRR_PUBLIC_KEY', default='')
TELEBIRR_NOTIFY_URL = config('TELEBIRR_NOTIFY_URL', default='')
TELEBIRR_REDIRECT_URL = config('TELEBIRR_REDIRECT_URL', default='')

# Onevas SMS / airtime charging
# ---------------------------------------------------------------------------
# TIMWE Master Aggregator
# ---------------------------------------------------------------------------
# Replaces the OneVAS block below. Both are configured during the migration;
# OneVAS is removed at cutover. TIMWE_INTEGRATION_ENABLED stays False until
# TIMWE supplies credentials and the WEB subscription flow, so the datasync
# endpoint records events without granting subscriptions alongside OneVAS.
TIMWE_INTEGRATION_ENABLED = config('TIMWE_INTEGRATION_ENABLED', default=False, cast=bool)
TIMWE_CHARGE_URL = config('TIMWE_CHARGE_URL', default='')
TIMWE_SP_ID = config('TIMWE_SP_ID', default='')
TIMWE_SP_PASSWORD = config('TIMWE_SP_PASSWORD', default='')
TIMWE_SERVICE_ID = config('TIMWE_SERVICE_ID', default='')
TIMWE_CURRENCY = config('TIMWE_CURRENCY', default='')
TIMWE_CHARGE_TIMEOUT = config('TIMWE_CHARGE_TIMEOUT', default=60, cast=int)
TIMWE_ALLOWED_IPS = [
    ip.strip() for ip in config('TIMWE_ALLOWED_IPS', default='').split(',') if ip.strip()
]
# Log the full inbound and outbound SOAP bodies for the datasync endpoint.
#
# On during onboarding, because the MA's requests are the only evidence of what
# it actually sends and the DB row alone cannot be watched live. Note what this
# puts in the log stream: the payload carries the subscriber's MSISDN, so this
# should be turned off once the integration is live and the traffic is real.
TIMWE_LOG_PAYLOADS = config('TIMWE_LOG_PAYLOADS', default=True, cast=bool)

ONEVAS_APPLICATION_KEY = config('ONEVAS_APPLICATION_KEY', default='')
ONEVAS_PRODUCT_NUMBER = config('ONEVAS_PRODUCT_NUMBER', default='')
ONEVAS_SMS_URL = config('ONEVAS_SMS_URL', default='https://onevas.et/api/partnerSms/send')
ONEVAS_CHARGING_URL = config('ONEVAS_CHARGING_URL', default='https://onevas.et/api/v1/charging')
ONEVAS_SPID = config('ONEVAS_SPID', default='')

#: Per-tier Onevas provisioning. These were previously a hardcoded dict of four
#: live application keys in ``api/views/subscription.py``. The authoritative copy
#: is the ``SubscriptionTier`` row; this mapping is the fallback used when a tier
#: has no value stored, and every entry now resolves through the secret chain.
ONEVAS_PRODUCTS = {
    tier: {
        'spid': config(f'ONEVAS_{tier.upper()}_SPID', default='') or ONEVAS_SPID,
        'service_id': config(f'ONEVAS_{tier.upper()}_SERVICE_ID', default=''),
        'product_id': config(f'ONEVAS_{tier.upper()}_PRODUCT_ID', default=''),
        'application_key': config(f'ONEVAS_{tier.upper()}_APPLICATION_KEY', default=''),
    }
    for tier in ('daily', 'weekly', 'monthly', 'ondemand')
}

# Firebase Cloud Messaging (mobile push)
FIREBASE_SERVER_KEY = config('FIREBASE_SERVER_KEY', default='')

# End-to-end encryption (X25519 / NaCl box) uses the application's identity
# keypair, which lives in Redis and is managed automatically at process
# startup -- see infrastructure/keys/ and common/security/e2e_encryption.py.
# There is deliberately no settings/env entry for it: Redis is the single
# source of truth, not configuration.

# Africa's Talking SMS. Legacy fallback path in `_send_sms`; Onevas is the
# primary SMS provider.
AT_USERNAME = config('AT_USERNAME', default='')
AT_API_KEY = config('AT_API_KEY', default='')


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

from common.constants.logging import build_logging_config  # noqa: E402

LOGGING = build_logging_config(level=config('LOG_LEVEL', default='INFO'), json_format=False)
