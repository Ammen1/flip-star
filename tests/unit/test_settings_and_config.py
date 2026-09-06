"""Unit tests for the configuration layer."""

import importlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Database resolution
# ---------------------------------------------------------------------------
#
# These take `hermetic_config` (tests/conftest.py) so resolution sees the
# environment and nothing else. Without it `monkeypatch.delenv` means only
# "absent from os.environ", and the ambient .env supplies the value instead --
# which made these two fail on a machine with DB_HOST set locally while
# passing in CI.


def test_use_docker_db_overrides_managed_host(monkeypatch, hermetic_config):
    """A stray RENDER var must not redirect a self-hosted deploy at a managed DB."""
    from infrastructure.database import config as db_config

    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('USE_DOCKER_DB', 'true')
    importlib.reload(db_config)

    assert db_config.is_managed_host() is False


def test_use_docker_db_selects_the_docker_postgres(monkeypatch, tmp_path, hermetic_config):
    """
    ``USE_DOCKER_DB=true`` means the docker-compose PostgreSQL, not SQLite.

    This replaces a previous ``test_local_config_defaults_to_sqlite``, which
    asserted that the same inputs produced ``SQLITE_ENGINE``. That assertion
    was wrong on both counts: ``SQLITE_ENGINE`` did not exist on the module
    (the test errored with ``AttributeError`` rather than failing on the
    comparison, which is why the real disagreement was hidden), and the
    application deliberately does the opposite of what it claimed.
    ``.env.example`` documents the flag as "Force the local/Docker PostgreSQL
    and ignore any managed-platform variables", ships it alongside
    ``DB_ENGINE=django.db.backends.postgresql``, and ``docker-compose.yml``
    sets both together. Verified directly: with ``USE_DOCKER_DB=true`` and no
    ``DB_ENGINE``, ``build_database_config`` returns the postgresql engine
    with ``HOST='postgres'`` -- the compose service name.

    There is no automatic downgrade to SQLite anywhere, by design (audit
    finding H-05); ``test_no_sqlite_fallback_helper_exists`` below guards that.
    """
    from infrastructure.database import config as db_config

    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('DB_ENGINE', raising=False)
    monkeypatch.delenv('DB_HOST', raising=False)
    monkeypatch.setenv('USE_DOCKER_DB', 'true')
    importlib.reload(db_config)

    resolved = db_config.build_database_config(tmp_path)
    assert resolved['ENGINE'] == db_config.POSTGRES_ENGINE
    assert resolved['HOST'] == 'postgres'


def test_sqlite_is_used_only_when_explicitly_requested(monkeypatch, tmp_path, hermetic_config):
    """SQLite is reachable, but only by asking for it by name."""
    from infrastructure.database import config as db_config

    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('DB_NAME', raising=False)
    monkeypatch.setenv('USE_DOCKER_DB', 'true')
    monkeypatch.setenv('DB_ENGINE', 'django.db.backends.sqlite3')
    importlib.reload(db_config)

    resolved = db_config.build_database_config(tmp_path)
    assert resolved['ENGINE'] == db_config.SQLITE_ENGINE
    assert resolved['NAME'] == str(tmp_path / 'db.sqlite3')


def test_no_sqlite_fallback_helper_exists():
    """
    The import-time DB probe that silently swapped in SQLite is gone.

    Guards audit finding H-05 from being reintroduced.
    """
    source = Path('infrastructure/database/config.py').read_text(encoding='utf-8')
    # Strip the module docstring, which describes the removed behaviour.
    body = source.split('"""', 2)[-1]

    assert 'fallback_db.sqlite3' not in body
    assert 'cursor.execute' not in body
    assert 'connection.cursor' not in body


# ---------------------------------------------------------------------------
# Storage resolution
# ---------------------------------------------------------------------------


def test_storage_falls_back_to_filesystem_without_credentials(monkeypatch, hermetic_config):
    from infrastructure.storage import config as storage_config

    for var in (
        'ACCESS_KEY_ID',
        'AWS_ACCESS_KEY_ID',
        'SECRET_ACCESS_KEY',
        'AWS_SECRET_ACCESS_KEY',
        'STORAGE_BUCKET_NAME',
        'AWS_STORAGE_BUCKET_NAME',
    ):
        monkeypatch.delenv(var, raising=False)
    importlib.reload(storage_config)

    resolved = storage_config.apply_storage_settings(media_url='/media/')
    assert resolved['default_file_storage'] == storage_config.FILESYSTEM_STORAGE
    assert resolved['media_url'] == '/media/'


def test_storage_accepts_legacy_aws_prefixed_names(monkeypatch, hermetic_config):
    """
    ``env.production.example`` documented AWS_-prefixed names the code did not
    read, silently disabling object storage (audit finding H-06). Both spellings
    must now work.
    """
    from infrastructure.storage import config as storage_config

    for var in ('ACCESS_KEY_ID', 'SECRET_ACCESS_KEY', 'STORAGE_BUCKET_NAME', 'S3_ENDPOINT_URL'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'key')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'secret')
    monkeypatch.setenv('AWS_STORAGE_BUCKET_NAME', 'flipstar-media')
    importlib.reload(storage_config)

    resolved = storage_config.apply_storage_settings(media_url='/media/')
    assert resolved['default_file_storage'] == storage_config.S3_STORAGE
    assert resolved['bucket_name'] == 'flipstar-media'


def test_storage_defaults_to_public_read_acl(monkeypatch, hermetic_config):
    """
    Uploaded media (profile photos, reel video/images) must be publicly
    readable. Without an explicit ACL, django-storages sends none at all and
    an object's readability falls back to the bucket's own default, which is
    private on most providers -- the actual upload succeeds but the file 404s
    for every viewer.
    """
    from infrastructure.storage import config as storage_config

    monkeypatch.delenv('S3_DEFAULT_ACL', raising=False)
    importlib.reload(storage_config)

    resolved = storage_config.apply_storage_settings(media_url='/media/')
    assert resolved['default_acl'] == 'public-read'


def test_storage_default_acl_can_be_disabled(monkeypatch, hermetic_config):
    """
    A bucket with S3 'Bucket owner enforced' Object Ownership rejects ACL
    headers outright -- an operator on such a bucket must be able to turn
    this off rather than have every upload fail.
    """
    from infrastructure.storage import config as storage_config

    monkeypatch.setenv('S3_DEFAULT_ACL', '')
    importlib.reload(storage_config)

    resolved = storage_config.apply_storage_settings(media_url='/media/')
    assert resolved['default_acl'] is None


# ---------------------------------------------------------------------------
# Log redaction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'message',
    [
        'Sending otp=123456 to user',
        'auth token: abcdef123456',
        'password=hunter2',
        'application_key: UPJG5ZM3X6C9',
    ],
)
def test_sensitive_values_are_redacted(message):
    import logging

    from common.constants.logging import REDACTION
    from common.middleware.logging import SensitiveDataFilter

    record = logging.LogRecord(
        name='test',
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    SensitiveDataFilter().filter(record)

    assert REDACTION in record.getMessage()


def test_ordinary_messages_pass_through_unchanged():
    import logging

    from common.middleware.logging import SensitiveDataFilter

    record = logging.LogRecord(
        name='test',
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='Processed reel 42 in 15ms',
        args=(),
        exc_info=None,
    )
    SensitiveDataFilter().filter(record)

    assert record.getMessage() == 'Processed reel 42 in 15ms'
