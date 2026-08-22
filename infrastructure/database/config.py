"""
Database connection resolution.

Extracted from ``config/settings.py`` so the resolution rules are readable and
testable in isolation.

One behaviour was deliberately removed: the original module opened a cursor and
ran ``SELECT 1`` while Django settings were still importing, and rewrote
``DATABASES`` to a local SQLite file if that query raised. A transient network
blip during startup therefore brought the service up healthy against an empty
throwaway database that accepted writes and vanished with the container. See
audit finding H-05. Connection failures now surface normally at first use.
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from typing import Any

from infrastructure.secrets import secret as config

POSTGRES_ENGINE = 'django.db.backends.postgresql'

#: The SQLite engine, selected only when DB_ENGINE explicitly asks for it.
#: This is NOT a fallback -- there is deliberately no automatic downgrade to
#: SQLite (audit finding H-05, see the module docstring). Named here rather
#: than left as a bare string in _local_or_docker so the two supported engines
#: are declared symmetrically and callers/tests have something to compare
#: against.
SQLITE_ENGINE = 'django.db.backends.sqlite3'

#: Environment variables checked, in order, for a connection URL.
DATABASE_URL_VARS = ('DATABASE_URL', 'POSTGRES_URL', 'POSTGRESQL_URL')


def _first_database_url() -> str | None:
    """Return the first non-empty connection URL from the known variables."""
    for name in DATABASE_URL_VARS:
        value = config(name, default=None) or os.environ.get(name)
        if value:
            return value
    return None


def _from_url(url: str) -> dict[str, Any]:
    """Build a PostgreSQL config from a connection URL."""
    parsed = urllib.parse.urlparse(url)
    return {
        'ENGINE': POSTGRES_ENGINE,
        'NAME': parsed.path.lstrip('/'),
        'USER': parsed.username,
        'PASSWORD': parsed.password,
        'HOST': parsed.hostname,
        'PORT': parsed.port or 5432,
        'OPTIONS': {'sslmode': config('DB_SSLMODE', default='require')},
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=0, cast=int),
    }


def _managed_postgres() -> dict[str, Any]:
    """Build a PostgreSQL config from discrete DB_* variables (managed host)."""
    return {
        'ENGINE': POSTGRES_ENGINE,
        'NAME': config('DB_NAME', default='neondb'),
        'USER': config('DB_USER', default=''),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default=''),
        'PORT': config('DB_PORT', default='5432'),
        'OPTIONS': {
            'sslmode': config('DB_SSLMODE', default='require'),
            'connect_timeout': 10,
        },
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=0, cast=int),
    }


def _local_or_docker(base_dir: Path) -> dict[str, Any]:
    """Build the config used for local development and the Docker stack."""
    engine = config('DB_ENGINE', default=POSTGRES_ENGINE)

    if engine == POSTGRES_ENGINE:
        return {
            'ENGINE': engine,
            'NAME': config('DB_NAME', default='flipstar_db'),
            'USER': config('DB_USER', default='flipstar_user'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='postgres'),
            'PORT': config('DB_PORT', default='5432'),
            'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=0, cast=int),
        }

    # Any other engine the operator explicitly asked for. In practice this is
    # SQLITE_ENGINE (local development without the docker-compose stack); the
    # NAME default is a file path, which only makes sense for SQLite.
    return {
        'ENGINE': engine,
        'NAME': config('DB_NAME', default=str(base_dir / 'db.sqlite3')),
    }


def is_managed_host() -> bool:
    """
    True when running on a managed platform that supplies its own database.

    ``USE_DOCKER_DB`` wins unconditionally so that a stray ``RENDER`` or
    ``DATABASE_URL`` left over from a previous deploy cannot silently redirect
    a self-hosted deployment at an old managed database.
    """
    if config('USE_DOCKER_DB', default=False, cast=bool):
        return False
    return bool(config('RENDER', default=False, cast=bool) or os.environ.get('RENDER'))


def build_database_config(base_dir: Path) -> dict[str, Any]:
    """Return the ``DATABASES['default']`` mapping for the current environment."""
    if not is_managed_host():
        return _local_or_docker(base_dir)

    url = _first_database_url()
    return _from_url(url) if url else _managed_postgres()
