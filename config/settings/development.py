"""Local development settings."""

from infrastructure.secrets import secret as config

from .base import *  # noqa: F401,F403

DEBUG = config('DEBUG', default=True, cast=bool)

# Convenience hosts for the Android emulator and LAN devices running Expo Go.
# These are development-only and must never appear in production settings.
for _host in ('192.168.1.8', '10.0.2.2', 'testserver', '*'):
    if _host not in ALLOWED_HOSTS:  # noqa: F405
        ALLOWED_HOSTS.append(_host)  # noqa: F405

CORS_ALLOW_ALL_ORIGINS = True

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@flipstar.local')

# Fall back to an in-process cache when Redis is not running locally, so a
# developer can boot the API without the full docker-compose stack. OTP
# verification still works because there is only one process.
if config('USE_LOCMEM_CACHE', default=False, cast=bool):
    CACHES = {  # noqa: F405
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'flipstar-dev',
        }
    }
    CHANNEL_LAYERS = {  # noqa: F405
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    }

from common.constants.logging import build_logging_config  # noqa: E402

LOGGING = build_logging_config(level=config('LOG_LEVEL', default='DEBUG'), json_format=False)
