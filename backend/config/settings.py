import os
import mimetypes
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-key')
DEBUG = config('DEBUG', default=False, cast=bool)

# ALLOWED_HOSTS: read from env, then guarantee critical hosts are present.
ALLOWED_HOSTS = [h.strip() for h in config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',') if h.strip()]
_required_hosts = [
    'localhost',
    '127.0.0.1',
    # 'postworq.onrender.com',
    # '.onrender.com',
    # Ethio Telecom production server
    'uat.flipstar.et',
    # Local network IPs for mobile app testing (Expo Go)
    '192.168.1.8',
    '10.0.2.2',
]
for _h in _required_hosts:
    if _h not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_h)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'channels',  # Django Channels for real-time WebSocket
    'django_celery_beat',  # Celery beat for scheduled tasks
    'api',
]

# Celery Configuration
CELERY_BROKER_URL = f"redis://{config('REDIS_HOST', default='127.0.0.1')}:{config('REDIS_PORT', default=6379)}/0"
CELERY_RESULT_BACKEND = f"redis://{config('REDIS_HOST', default='127.0.0.1')}:{config('REDIS_PORT', default=6379)}/0"
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# CORS settings
CORS_ALLOWED_ORIGINS = [
    'https://uat.flipstar.et',
    'http://localhost:3000',
    'http://localhost:5173',
    'http://localhost:5174',
]
CORS_ALLOW_ALL_ORIGINS = True  # Fallback to allow all origins

MIDDLEWARE = [
    'api.middleware.CustomCorsMiddleware',  # Custom CORS for Vercel - handles all origins
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]

ROOT_URLCONF = 'config.urls'

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

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Django Channels configuration for Redis channel layer
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [(config('REDIS_HOST', default='127.0.0.1'), int(config('REDIS_PORT', default=6379)))],
        },
    },
}

# Auto-detect Render environment (RENDER env var is set automatically by Render)
IS_RENDER = config('RENDER', default=False, cast=bool) or os.environ.get('RENDER', False)

# Explicit override for self-hosted Docker deployments (e.g. Ethio Telecom server).
# When USE_DOCKER_DB=true is set in the .env, we ALWAYS use the local Docker
# postgres service regardless of RENDER / DATABASE_URL being present. This
# prevents the app from silently connecting to an old Neon database if stray
# env vars are carried over from a previous deploy.
USE_DOCKER_DB = config('USE_DOCKER_DB', default=False, cast=bool)
if USE_DOCKER_DB:
    IS_RENDER = False

# Database configuration
if IS_RENDER:
    # Render deployment: Use Neon database
    # Check for multiple possible environment variable names
    database_url = (config('DATABASE_URL', default=None) or
                    config('POSTGRES_URL', default=None) or
                    config('POSTGRESQL_URL', default=None) or
                    os.environ.get('DATABASE_URL') or
                    os.environ.get('POSTGRES_URL') or
                    os.environ.get('POSTGRESQL_URL'))

    if database_url:
        # Parse DATABASE_URL
        import urllib.parse
        parsed = urllib.parse.urlparse(database_url)
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': parsed.path.lstrip('/'),
                'USER': parsed.username,
                'PASSWORD': parsed.password,
                'HOST': parsed.hostname,
                'PORT': parsed.port or 5432,
                'OPTIONS': {
                    'sslmode': 'require',
                },
                'CONN_MAX_AGE': 0,
            }
        }
        print(f"=== USING DATABASE_URL ===")
        print(f"DATABASE_HOST: {parsed.hostname}")
        print(f"DATABASE_NAME: {parsed.path.lstrip('/')}")
    else:
        # Fallback to individual environment variables
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': config('DB_NAME', default='neondb'),
                'USER': config('DB_USER', default='neondb_owner'),
                'PASSWORD': config('DB_PASSWORD', default='your-db-password-here'),
                'HOST': config('DB_HOST', default='your-db-host-here'),
                'PORT': config('DB_PORT', default='5432'),
                'OPTIONS': {
                    'sslmode': 'require',
                    'connect_timeout': 10,
                },
                'CONN_MAX_AGE': 0,
            }
        }
        print(f"=== USING INDIVIDUAL ENV VARS ===")
        print(f"DATABASE_HOST: {DATABASES['default']['HOST']}")

    # Debug: Print database configuration (remove in production)
    print(f"=== NEW DEPLOYMENT DETECTED ===")
    print(f"DATABASE_HOST: {DATABASES['default']['HOST']}")
    print(f"DATABASE_NAME: {DATABASES['default']['NAME']}")
    print(f"DATABASE_USER: {DATABASES['default']['USER']}")
    print(f"=== DEPLOYMENT VERSION: 3.0 ===")

    # Test database connection and handle errors gracefully
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        print("=== DATABASE CONNECTION SUCCESSFUL ===")
    except Exception as e:
        print(f"=== DATABASE CONNECTION FAILED: {e} ===")
        print("=== FALLBACK TO SQLITE FOR CRITICAL OPERATIONS ===")
        # Fallback to SQLite for basic functionality
        DATABASES['default'] = {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(BASE_DIR / 'fallback_db.sqlite3'),
        }
else:
    # Local / Docker development
    _db_engine = config('DB_ENGINE', default='django.db.backends.sqlite3')
    if _db_engine == 'django.db.backends.postgresql':
        DATABASES = {
            'default': {
                'ENGINE': _db_engine,
                'NAME': config('DB_NAME', default='flipstar_db'),
                'USER': config('DB_USER', default='flipstar_user'),
                'PASSWORD': config('DB_PASSWORD', default='changeme'),
                'HOST': config('DB_HOST', default='postgres'),
                'PORT': config('DB_PORT', default='5432'),
            }
        }
    else:
        DATABASES = {
            'default': {
                'ENGINE': _db_engine,
                'NAME': config('DB_NAME', default=str(BASE_DIR / 'db.sqlite3')),
            }
        }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Addis_Ababa'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Backend URL for building absolute URLs in API responses
# This is used by serializers to construct full URLs for media files
BACKEND_URL = config('BACKEND_URL', default='https://uat.flipstar.et')

# S3/MinIO storage configuration
S3_ACCESS_KEY_ID = config('ACCESS_KEY_ID', default='')
S3_SECRET_ACCESS_KEY = config('SECRET_ACCESS_KEY', default='')
S3_BUCKET_NAME = config('STORAGE_BUCKET_NAME', default='')
S3_REGION_NAME = config('REGION_NAME', default='us-east-1')
S3_ENDPOINT_URL = config('S3_ENDPOINT_URL', default='')
S3_CUSTOM_DOMAIN = f'{S3_BUCKET_NAME}.s3.amazonaws.com' if S3_BUCKET_NAME else None

# Use S3/MinIO for media storage if credentials are provided
if S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY and S3_BUCKET_NAME:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    # Use WhiteNoise for static files, S3 only for media
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
    
    # S3 storage settings
    S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    S3_FILE_OVERWRITE = False
    S3_DEFAULT_ACL = None
    
    # If S3_ENDPOINT_URL is set, use MinIO (self-hosted), otherwise use AWS S3
    if S3_ENDPOINT_URL:
        AWS_S3_ENDPOINT_URL = S3_ENDPOINT_URL
        AWS_S3_USE_SSL = False
        MEDIA_URL = f'{S3_ENDPOINT_URL}/{S3_BUCKET_NAME}/media/'
        # Static files served by WhiteNoise, not S3
    else:
        # AWS S3
        MEDIA_URL = f'https://{S3_CUSTOM_DOMAIN}/media/'
        # Static files served by WhiteNoise, not S3
else:
    # Local storage
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Configure mimetypes for video files
mimetypes.add_type('video/mp4', '.mp4', True)
mimetypes.add_type('video/webm', '.webm', True)
mimetypes.add_type('video/ogg', '.ogv', True)

# Streaming response settings
STREAMING_CONTENT_LENGTH = 4096

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
}

CORS_ALLOWED_ORIGINS = [
    "https://uat.flipstar.et",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

# Allow all origins to fix CORS issues
CORS_ALLOW_ALL_ORIGINS = True
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
]
CORS_EXPOSE_HEADERS = [
    'content-type',
    'x-csrftoken',
]

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB

# Trust X-Forwarded-Proto header from nginx for HTTPS behind reverse proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ─── Web Push (VAPID) ───────────────────────────────────────────────────────
# Generate keys once with:
#   python -m py_vapid --gen --applicationServerKey
# Then set them as env vars VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY / VAPID_SUBJECT.
# VAPID_PUBLIC_KEY is what the frontend sends to PushManager.subscribe().
VAPID_PUBLIC_KEY = config('VAPID_PUBLIC_KEY', default='')
VAPID_PRIVATE_KEY = config('VAPID_PRIVATE_KEY', default='')
VAPID_SUBJECT = config('VAPID_SUBJECT', default='mailto:admin@flipstar.et')

# ─── Telebirr Direct Debit (SOAP API) ───────────────────────────────────────
# SOAP API endpoint for direct debit mandate operations
TELEBIRR_SOAP_URL = config('TELEBIRR_SOAP_URL', default='http://10.180.79.13:30001/payment/services/APIRequestMgrService')
TELEBIRR_THIRD_PARTY_ID = config('TELEBIRR_THIRD_PARTY_ID', default='TestMer')
TELEBIRR_THIRD_PARTY_PASSWORD = config('TELEBIRR_THIRD_PARTY_PASSWORD', default='jIfxwUU1S7jJmh1dgP3+wK3fd4Qxlxxcc4cb4i0z4Tk=')
TELEBIRR_SHORTCODE = config('TELEBIRR_SHORTCODE', default='232323')
TELEBIRR_RESULT_URL = config('TELEBIRR_RESULT_URL', default='https://196.189.236.140/api/webhooks/telebirr-direct-debit/')
TELEBIRR_PAYEE_ACCOUNT_NAME = config('TELEBIRR_PAYEE_ACCOUNT_NAME', default='Flipstar')
TELEBIRR_CALLER_TYPE = config('TELEBIRR_CALLER_TYPE', default='2')  # 2 = Third Party

# SP Operator credentials for SOAP API
TELEBIRR_SP_OPERATOR_ID = config('TELEBIRR_SP_OPERATOR_ID', default='TestSPOperAPI')
TELEBIRR_SP_OPERATOR_CREDENTIAL = config('TELEBIRR_SP_OPERATOR_CREDENTIAL', default='2JKSrKYlLAVvKWuIUXcexc3GHiT0+lEKzeVb6JRcZUM=')

# Organization Operator credentials for SOAP API (InitTrans)
TELEBIRR_ORG_OPERATOR_ID = config('TELEBIRR_ORG_OPERATOR_ID', default='TestAPI')
TELEBIRR_ORG_OPERATOR_CREDENTIAL = config('TELEBIRR_ORG_OPERATOR_CREDENTIAL', default='w6byUD48WhFJzIqacTA1i/SBhBhzSbfRdQMvkEzOs6M=')

# ─── Onevas SMS Configuration ─────────────────────────────────────────────────────
ONEVAS_APPLICATION_KEY = config('ONEVAS_APPLICATION_KEY', default='UPJG5ZM3X6C9LLDSKKCME4MA86UQRKWV')
ONEVAS_PRODUCT_NUMBER = config('ONEVAS_PRODUCT_NUMBER', default='10000302850')
