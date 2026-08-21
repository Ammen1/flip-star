"""Settings used by the test suite.

Optimised for speed and isolation: in-memory database and cache, no real
network, synchronous Celery, and a fast password hasher.
"""

import os

from .base import *  # noqa: F401,F403

DEBUG = False
TESTING = True

ALLOWED_HOSTS = ['*']

# SQLite in-memory by default -- fast, and every non-concurrency test only
# needs a schema to exist, not real transaction/locking semantics.
#
# Opt-in override for the concurrency test suite (tests/integration/test_concurrency.py),
# which specifically exercises PostgreSQL's SELECT ... FOR UPDATE and
# conditional-UPDATE row-locking -- behavior SQLite doesn't meaningfully
# have, so those tests skip themselves unless this is set:
#
#   TEST_DB_ENGINE=postgresql TEST_DB_NAME=... TEST_DB_USER=... \
#   TEST_DB_PASSWORD=... TEST_DB_HOST=... TEST_DB_PORT=... pytest tests/integration/test_concurrency.py
if os.environ.get('TEST_DB_ENGINE') == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('TEST_DB_NAME', 'test_flipstar'),
            'USER': os.environ.get('TEST_DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('TEST_DB_PASSWORD', ''),
            'HOST': os.environ.get('TEST_DB_HOST', '127.0.0.1'),
            'PORT': os.environ.get('TEST_DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'flipstar-test',
    }
}

CHANNEL_LAYERS = {
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
}

# Run tasks inline so tests assert on their effects without a broker.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Keep test output readable.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'null': {'class': 'logging.NullHandler'}},
    'root': {'handlers': ['null'], 'level': 'CRITICAL'},
}
