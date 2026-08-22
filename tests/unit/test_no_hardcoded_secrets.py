"""
Guards the rule that configuration comes from the secret chain, never from a
literal in source or a direct .env read.

Two ways this regresses:

1. A module imports ``decouple.config`` directly. That reads the environment and
   .env only -- Vault is never consulted, so a value rotated in Vault is ignored
   and the module silently keeps using a stale one.
2. A credential is written as a literal default, e.g.
   ``config('ONEVAS_APPLICATION_KEY', default='UPJG5ZM3X6C9...')``. The value
   then ships in the repository and survives any rotation.

Both were present before the Vault migration. These tests stop them returning.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[2]

SEARCH_ROOTS = ('api', 'common', 'config', 'infrastructure')
SKIP_PARTS = {'migrations', '__pycache__', '.venv', 'node_modules', 'tests'}

#: The only module allowed to import decouple: it *is* the .env fallback layer.
DECOUPLE_ALLOWED = {Path('infrastructure/secrets/provider.py')}

#: Credential-shaped setting names. A literal default for any of these is a leak.
SECRET_NAME = re.compile(
    r"""(?ix)
    \b(
        [A-Z_]*(?:PASSWORD|SECRET|CREDENTIAL|APPLICATION_KEY|API_KEY|PRIVATE_KEY|TOKEN)[A-Z_]*
    )\b
    """
)

#: `config('NAME', default='literal')` / `secret('NAME', default="literal")`
DEFAULTED_CALL = re.compile(
    r"""(?x)
    \b(?:config|secret)\s*\(\s*
    ['"](?P<name>[A-Z0-9_]+)['"]\s*,\s*
    default\s*=\s*
    ['"](?P<value>[^'"]*)['"]
    """
)

#: Values that are safe as defaults even on a credential-shaped name.
#:
#: `django-insecure-key` is Django's own marker for "this is a placeholder, not
#: a key". It is allowed here only because config/settings/production.py lists
#: it in FORBIDDEN_VALUES and refuses to start when it reaches production, so it
#: cannot be deployed by accident. See test_insecure_secret_key_is_blocked below.
BENIGN_DEFAULTS = {
    '',
    'django-insecure-key',
    'mailto:admin@flipstar.et',
    'superadmin',
    'admin@example.com',
}


def source_files():
    for root in SEARCH_ROOTS:
        for path in (BACKEND / root).rglob('*.py'):
            if SKIP_PARTS & set(path.parts):
                continue
            yield path


def relative(path):
    return path.relative_to(BACKEND)


def test_no_module_imports_decouple_directly():
    """Only the .env fallback layer may import decouple."""
    offenders = []
    for path in source_files():
        text = path.read_text(encoding='utf-8')
        if re.search(r'^\s*(from decouple import|import decouple)', text, re.MULTILINE):
            rel = relative(path)
            if rel not in DECOUPLE_ALLOWED:
                offenders.append(str(rel).replace('\\', '/'))

    assert not offenders, (
        'These modules read configuration directly from decouple, bypassing Vault:\n  '
        + '\n  '.join(offenders)
        + '\n\nUse `from infrastructure.secrets import secret`, or read the value '
          'from django.conf.settings.'
    )


def test_no_credential_has_a_literal_default():
    """A credential-shaped setting must not carry a value in source."""
    offenders = []
    for path in source_files():
        for match in DEFAULTED_CALL.finditer(path.read_text(encoding='utf-8')):
            name, value = match.group('name'), match.group('value')
            if not SECRET_NAME.search(name):
                continue
            if value in BENIGN_DEFAULTS:
                continue
            offenders.append(f'{relative(path)}: {name} defaults to a literal')

    assert not offenders, (
        'Credentials must not have literal defaults:\n  ' + '\n  '.join(offenders)
    )


def test_no_onevas_application_keys_in_source():
    """The four live per-tier Onevas keys must not reappear.

    They were hardcoded in `api/views/subscription.py` as ONEVAS_PRODUCTS.
    Matched by shape -- a 32-character uppercase alphanumeric run -- rather than
    by value, so the test does not itself contain a credential.
    """
    shape = re.compile(r"['\"][A-Z0-9]{32}['\"]")
    offenders = []
    for path in source_files():
        for line in path.read_text(encoding='utf-8').splitlines():
            if shape.search(line) and 'default=' not in line:
                offenders.append(f'{relative(path)}: {line.strip()[:70]}')

    assert not offenders, (
        'Possible hardcoded provider key(s):\n  ' + '\n  '.join(offenders)
    )


def test_admin_password_has_no_insecure_default():
    """`Admin123!` shipped as the default superuser password in two places."""
    offenders = []
    for path in source_files():
        text = path.read_text(encoding='utf-8')
        if 'Admin123!' in text:
            offenders.append(str(relative(path)).replace('\\', '/'))

    assert not offenders, (
        'Insecure default admin password present in:\n  ' + '\n  '.join(offenders)
    )


def test_insecure_secret_key_is_blocked_in_production():
    """The development SECRET_KEY placeholder must never be deployable.

    It is permitted as a default only because production refuses to boot with it.
    If that guard is ever removed, this fails.
    """
    source = (BACKEND / 'config' / 'settings' / 'production.py').read_text(encoding='utf-8')

    assert 'FORBIDDEN_VALUES' in source
    assert 'django-insecure-key' in source, (
        'production.py no longer rejects the development SECRET_KEY placeholder'
    )


@pytest.mark.parametrize(
    'name',
    [
        'ONEVAS_APPLICATION_KEY',
        'ONEVAS_PRODUCT_NUMBER',
        'ONEVAS_SMS_URL',
        'ONEVAS_CHARGING_URL',
        'ONEVAS_PRODUCTS',
        'FIREBASE_SERVER_KEY',
        'AT_USERNAME',
        'AT_API_KEY',
        'TELEBIRR_SOAP_URL',
        'TELEBIRR_THIRD_PARTY_PASSWORD',
        'VAPID_PRIVATE_KEY',
        'REDIS_HOST',
        'REDIS_PORT',
    ],
)
def test_setting_is_exposed_for_runtime_lookup(settings, name):
    """Every value runtime code reads must exist on settings.

    Modules now read `settings.X` instead of re-reading the environment, so a
    missing entry is an AttributeError at request time rather than a silent
    fallback.
    """
    assert hasattr(settings, name), f'settings.{name} is not defined'
