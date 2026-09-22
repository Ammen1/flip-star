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
        # POST /posts/media/: fresh media URLs for posts a client already has.
        # A long feed session refreshes in batches of up to 20 posts.
        'media_refresh': '120/min',
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
# Lifetime of those signatures (seconds); see docs/media-pipeline.md, "When a
# video will not load".
AWS_QUERYSTRING_EXPIRE = _storage['querystring_expire']
AWS_S3_OBJECT_PARAMETERS = _storage['object_parameters']

# Video MIME types must be registered for range-request streaming to work.
mimetypes.add_type('video/mp4', '.mp4', True)
mimetypes.add_type('video/webm', '.webm', True)
mimetypes.add_type('video/ogg', '.ogv', True)
# Processed stills are also written as WebP; older mimetypes tables lack it,
# and an object stored without its type is served as application/octet-stream.
mimetypes.add_type('image/webp', '.webp', True)

STREAMING_CONTENT_LENGTH = 4096

FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB

# Media pipeline: api/services/media_pipeline.py (upload intake) and
# api/tasks/media.py (processing). Documented in infrastructure/config/schema.py.
MEDIA_MAX_UPLOAD_BYTES = config('MEDIA_MAX_UPLOAD_BYTES', default=50 * 1024 * 1024, cast=int)
MEDIA_MAX_VIDEO_SECONDS = config('MEDIA_MAX_VIDEO_SECONDS', default=120, cast=int)
MEDIA_MAX_IMAGE_PIXELS = config('MEDIA_MAX_IMAGE_PIXELS', default=40_000_000, cast=int)
# 0 keeps originals indefinitely -- the current behaviour, and the safe default
# until someone decides re-processing from source is no longer needed.
MEDIA_SOURCE_RETENTION_DAYS = config('MEDIA_SOURCE_RETENTION_DAYS', default=0, cast=int)


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
    # Lets a retried upload find the post it already created (see
    # api/services/media_pipeline.py:read_client_upload_id).
    'idempotency-key',
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
# Whether SOAP calls to the Telebirr gateway verify the server certificate.
# The provider's testbed endpoints (internal IPs such as 10.180.70.177) serve
# a private certificate that is not chain-trusted locally, so verification is
# OFF by default -- the pre-existing behavior before TELEBIRR_VERIFY_SSL was
# introduced. Set it to true in a deployment that has the provider's CA
# installed and trusts the chain.
TELEBIRR_VERIFY_SSL = config('TELEBIRR_VERIFY_SSL', default=False, cast=bool)

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
# The account a payout leaves FROM. Separate from TELEBIRR_SHORTCODE, which
# is the C2B code money arrives at: telebirr issues a different short code for
# each direction, and sending the C2B one on a B2C request -- or, as happened
# here, sending an empty element because the shared setting was never set --
# is refused by the gateway with no useful reason. Falls back to
# TELEBIRR_SHORTCODE so nothing changes for a deployment that has only one.
TELEBIRR_B2C_SHORTCODE = config('TELEBIRR_B2C_SHORTCODE', default='53906')
TELEBIRR_B2C_SERVICE_CODE = config('TELEBIRR_B2C_SERVICE_CODE', default='53906')
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

# ---------------------------------------------------------------------------
# TIMWE Master Aggregator
# ---------------------------------------------------------------------------
# The subscription and SMS channel. It replaced OneVAS, which has been removed
# -- no ONEVAS_* setting exists or is read. TIMWE_INTEGRATION_ENABLED decides
# whether datasync notifications grant subscriptions or are only recorded.
TIMWE_INTEGRATION_ENABLED = config('TIMWE_INTEGRATION_ENABLED', default=False, cast=bool)
TIMWE_CHARGE_URL = config('TIMWE_CHARGE_URL', default='')
TIMWE_SP_ID = config('TIMWE_SP_ID', default='')
TIMWE_SP_PASSWORD = config('TIMWE_SP_PASSWORD', default='')
TIMWE_SERVICE_ID = config('TIMWE_SERVICE_ID', default='')
TIMWE_CURRENCY = config('TIMWE_CURRENCY', default='')
TIMWE_CHARGE_TIMEOUT = config('TIMWE_CHARGE_TIMEOUT', default=60, cast=int)
# Where TIMWE's own working chargeAmount example differs from their written
# guide. Defaults are the guide; set these from what their gateway actually
# accepts. TIMWE_CHARGE_SERVICE_ID falls back to TIMWE_SERVICE_ID, which is the
# service their subscription notifications carry -- charging may be another.
TIMWE_CHARGE_SERVICE_ID = config('TIMWE_CHARGE_SERVICE_ID', default='')
# The MA's charging code, sent as <code>. Optional per the guide (p.21).
TIMWE_CHARGE_CODE = config('TIMWE_CHARGE_CODE', default='')
# endUserIdentifier as 'tel:2519...' (the guide's field table) or bare digits
# (what TIMWE's example sends).
TIMWE_CHARGE_TEL_PREFIX = config('TIMWE_CHARGE_TEL_PREFIX', default=True, cast=bool)
# 'md5' is the guide: spPassword = MD5(spId + Password + timeStamp), and the
# account password never crosses the wire. 'plain' sends the password itself,
# which is what TIMWE's own working example does; it is refused over plain
# HTTP, because it puts the password in every charge request.
TIMWE_CHARGE_AUTH_MODE = config('TIMWE_CHARGE_AUTH_MODE', default='md5')
# TIMWE serve chargeAmount over HTTPS on an IP address with a certificate no
# public CA vouches for. Point this at their certificate file and only that
# certificate is trusted -- the setting to prefer.
TIMWE_CHARGE_CA_BUNDLE = config('TIMWE_CHARGE_CA_BUNDLE', default='')
# The fallback while that file is being obtained: still encrypted, but no
# longer proof of who is on the other end. Every charge sent this way logs
# TIMWE_CHARGE_TLS_UNVERIFIED. Must stay true in production.
TIMWE_CHARGE_VERIFY_TLS = config('TIMWE_CHARGE_VERIFY_TLS', default=True, cast=bool)
# Coin purchase via airtime, charged through TIMWE chargeAmount. OFF by default
# and deliberately so: the flow was disabled by policy ("Ethio Telecom SIM
# cards are only accessible for SMS OTP verification"). Turning it on reverses
# that policy -- a business decision, not a deployment one. It also needs the
# five TIMWE_CHARGE/SP/SERVICE/CURRENCY values above, which TIMWE supplies.
TIMWE_AIRTIME_PURCHASE_ENABLED = config('TIMWE_AIRTIME_PURCHASE_ENABLED', default=False, cast=bool)
# Master switch for TIMWE chargeAmount. While false, no charge request leaves
# the process whatever else is configured -- deploying the code must never be
# what starts charging subscribers. Each flow also needs its own switch.
TIMWE_CHARGING_ENABLED = config('TIMWE_CHARGING_ENABLED', default=False, cast=bool)
# Automatic renewal of an expired short-code subscription: when a TIMWE SMS
# subscriber's period runs out, the backend charges their registered number
# once for the next period (api/services/subscription_renewal.py). OFF by
# default, and must stay off unless TIMWE confirms it does NOT renew these
# subscriptions itself -- if it does, a charge from here is a second charge
# for the same period.
TIMWE_SUBSCRIPTION_RENEWAL_ENABLED = config(
    'TIMWE_SUBSCRIPTION_RENEWAL_ENABLED', default=False, cast=bool
)
# While renewal is on, an hourly beat job charges every lapsed airtime
# subscription that is due. A charge TIMWE refused -- low balance, the MA
# unreachable -- took nothing, so it is tried again this many minutes later...
TIMWE_RENEWAL_RETRY_MINUTES = config('TIMWE_RENEWAL_RETRY_MINUTES', default=60, cast=int)
# ...for up to this many days after the period ran out. After that the
# subscription is left expired and the subscriber opts in again on the short code.
TIMWE_RENEWAL_WINDOW_DAYS = config('TIMWE_RENEWAL_WINDOW_DAYS', default=7, cast=int)
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

# Firebase Cloud Messaging (mobile push)
FIREBASE_SERVER_KEY = config('FIREBASE_SERVER_KEY', default='')

# End-to-end encryption (X25519 / NaCl box) uses the application's identity
# keypair, which lives in Redis and is managed automatically at process
# startup -- see infrastructure/keys/ and common/security/e2e_encryption.py.
# There is deliberately no settings/env entry for it: Redis is the single
# source of truth, not configuration.


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

from common.constants.logging import build_logging_config  # noqa: E402

LOGGING = build_logging_config(level=config('LOG_LEVEL', default='INFO'), json_format=False)

# Where the welcome SMS sends a new subscriber to redeem their OTP.
TIMWE_SUBSCRIPTION_LINK_BASE = config(
    'TIMWE_SUBSCRIPTION_LINK_BASE', default='https://uat.flipstar.et/register'
)

# ---------------------------------------------------------------------------
# SMS delivery
# ---------------------------------------------------------------------------
# TIMWE SMPP is the transport for every application SMS, OTPs included. OneVAS
# has been removed and there is deliberately no fallback: failing over to
# another gateway would hide an SMPP outage instead of surfacing it.
#
# 'console' exists for local development, where there is no gateway to reach.
# Production must set 'timwe_smpp' explicitly -- api/services/sms/__init__.py
# refuses to start on an unknown value rather than picking one.
SMS_PROVIDER = config('SMS_PROVIDER', default='timwe_smpp')

# The short code subscribers text to subscribe and send STOP to. TIMWE's now;
# it was OneVAS's, and this replaces the ONEVAS_SHORT_CODE that went with it.
SMS_SHORT_CODE = config('SMS_SHORT_CODE', default='9286')

# The SMPP link. Separate from TIMWE_SP_ID/TIMWE_SP_PASSWORD above, which are
# the HTTP charging API's credentials -- see infrastructure/config/schema.py.
TIMWE_SMPP_HOST = config('TIMWE_SMPP_HOST', default='')
TIMWE_SMPP_PORT = config('TIMWE_SMPP_PORT', default=0, cast=int)
TIMWE_SMPP_SYSTEM_ID = config('TIMWE_SMPP_SYSTEM_ID', default='')
TIMWE_SMPP_PASSWORD = config('TIMWE_SMPP_PASSWORD', default='')
TIMWE_SMPP_SYSTEM_TYPE = config('TIMWE_SMPP_SYSTEM_TYPE', default='')

# Addressing. TON/NPI defaults follow the common Ethiopian short-code setup:
# an international destination MSISDN (251...) and a national short code as
# the source. TIMWE may require different values -- they are settings, not
# constants, for exactly that reason.
TIMWE_SMPP_SOURCE_ADDR = config('TIMWE_SMPP_SOURCE_ADDR', default='')
TIMWE_SMPP_SOURCE_TON = config('TIMWE_SMPP_SOURCE_TON', default=3, cast=int)
TIMWE_SMPP_SOURCE_NPI = config('TIMWE_SMPP_SOURCE_NPI', default=0, cast=int)
TIMWE_SMPP_DEST_TON = config('TIMWE_SMPP_DEST_TON', default=1, cast=int)
TIMWE_SMPP_DEST_NPI = config('TIMWE_SMPP_DEST_NPI', default=1, cast=int)
TIMWE_SMPP_SERVICE_TYPE = config('TIMWE_SMPP_SERVICE_TYPE', default='')

# 1 = ask for a delivery receipt. Without it a message can only ever reach
# 'submitted' -- the gateway accepted it -- and never 'delivered'.
TIMWE_SMPP_REGISTERED_DELIVERY = config('TIMWE_SMPP_REGISTERED_DELIVERY', default=1, cast=int)
TIMWE_SMPP_ENQUIRE_LINK_SECONDS = config('TIMWE_SMPP_ENQUIRE_LINK_SECONDS', default=30, cast=int)

# SMPP is one long-lived TCP session, so exactly one process may own it. SMS
# tasks are routed to their own queue, consumed by a single-replica worker
# running --pool=solo; the general workers (2 replicas x concurrency 4) never
# see this queue. See k8s/base/deployment-sms-worker.yaml.
CELERY_TASK_ROUTES = {
    'api.tasks.sms.*': {'queue': 'sms'},
}

# True only in the dedicated SMS worker, which owns the single SMPP session.
# Set by k8s/base/deployment-sms-worker.yaml; every other process leaves it
# false and never binds. See api/celery.py.
SMS_WORKER = config('SMS_WORKER', default=False, cast=bool)
