"""
Tests for secret resolution.

The provider decides where every credential in the system comes from, so its
precedence rules need to be pinned. A silent change here would either expose a
stale secret or fail to pick up a rotated one.
"""

import pytest
from decouple import UndefinedValueError

from infrastructure.secrets.provider import SecretProvider
from infrastructure.secrets.vault import VaultUnavailable

pytestmark = pytest.mark.unit


class FakeVault:
    """Stands in for VaultClient so tests never touch the network."""

    def __init__(self, secrets=None, fail=False):
        self._secrets = secrets or {}
        self._fail = fail
        self.load_calls = 0

    @classmethod
    def factory(cls, secrets=None, fail=False):
        """Return a `from_env`-compatible constructor bound to fixed data."""
        def _from_env(env=None):
            return cls(secrets=secrets, fail=fail)
        return _from_env

    def load(self):
        self.load_calls += 1
        return {} if self._fail else dict(self._secrets)

    def load_or_raise(self):
        self.load_calls += 1
        if self._fail:
            raise VaultUnavailable('simulated Vault outage')
        return dict(self._secrets)


@pytest.fixture
def use_vault(monkeypatch):
    """Install a fake Vault and return a helper to configure its contents."""
    def _install(secrets=None, fail=False):
        monkeypatch.setattr(
            'infrastructure.secrets.provider.VaultClient',
            type('StubVaultClient', (), {'from_env': staticmethod(FakeVault.factory(secrets, fail))}),
        )
    return _install


# ---------------------------------------------------------------------------
# Vault disabled — behaviour must match the pre-Vault project exactly
# ---------------------------------------------------------------------------

def test_resolves_from_environment_when_vault_disabled():
    provider = SecretProvider(env={'DB_NAME': 'flipstar_db'})
    assert provider.get('DB_NAME') == 'flipstar_db'


def test_returns_default_when_absent():
    provider = SecretProvider(env={})
    assert provider.get('TOTALLY_ABSENT_KEY', default='fallback') == 'fallback'


def test_raises_when_absent_and_no_default():
    provider = SecretProvider(env={})
    with pytest.raises(UndefinedValueError):
        provider.get('TOTALLY_ABSENT_KEY')


def test_vault_disabled_reports_correctly():
    provider = SecretProvider(env={})
    assert provider.vault_enabled is False
    assert provider.describe()['vault_enabled'] is False


# ---------------------------------------------------------------------------
# Casting — must match decouple so the 55 existing call sites behave the same
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    'raw,expected',
    [('true', True), ('True', True), ('1', True), ('yes', True), ('on', True),
     ('false', False), ('False', False), ('0', False), ('no', False), ('', False)],
)
def test_bool_casting_matches_decouple(raw, expected):
    provider = SecretProvider(env={'FLAG': raw})
    assert provider.get('FLAG', cast=bool) is expected


def test_bool_casting_applies_to_default():
    provider = SecretProvider(env={})
    assert provider.get('MISSING_FLAG', default=True, cast=bool) is True


def test_int_casting():
    provider = SecretProvider(env={'PORT': '5432'})
    assert provider.get('PORT', cast=int) == 5432


def test_invalid_cast_raises_with_key_name():
    provider = SecretProvider(env={'PORT': 'not-a-number'})
    with pytest.raises(ValueError, match='PORT'):
        provider.get('PORT', cast=int)


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------

def test_environment_outranks_vault_by_default(use_vault):
    use_vault({'DB_PASSWORD': 'from-vault'})
    provider = SecretProvider(env={'VAULT_ADDR': 'http://vault:8200', 'DB_PASSWORD': 'from-env'})

    assert provider.get('DB_PASSWORD') == 'from-env'


def test_vault_outranks_environment_when_configured(use_vault):
    use_vault({'DB_PASSWORD': 'from-vault'})
    provider = SecretProvider(
        env={
            'VAULT_ADDR': 'http://vault:8200',
            'VAULT_PRECEDENCE': 'vault',
            'DB_PASSWORD': 'from-env',
        }
    )

    assert provider.get('DB_PASSWORD') == 'from-vault'


def test_vault_used_when_key_absent_from_environment(use_vault):
    use_vault({'TELEBIRR_THIRD_PARTY_PASSWORD': 'secret-value'})
    provider = SecretProvider(env={'VAULT_ADDR': 'http://vault:8200'})

    assert provider.get('TELEBIRR_THIRD_PARTY_PASSWORD') == 'secret-value'


def test_vault_payload_is_fetched_once(use_vault):
    use_vault({'A': '1', 'B': '2', 'C': '3'})
    provider = SecretProvider(env={'VAULT_ADDR': 'http://vault:8200'})

    provider.get('A')
    provider.get('B')
    provider.get('C')

    # One network read for the whole path, not one per key.
    assert provider._vault.load_calls == 1


# ---------------------------------------------------------------------------
# Bootstrap keys must never be read from Vault (that would be circular)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('key', ['VAULT_TOKEN', 'VAULT_ROLE_ID', 'DJANGO_SETTINGS_MODULE'])
def test_bootstrap_keys_absent_from_env_ignore_vault(use_vault, key):
    """A bootstrap key not in the environment falls to its default, not Vault."""
    use_vault({key: 'should-be-ignored'})
    provider = SecretProvider(env={'VAULT_ADDR': 'http://vault:8200'})

    assert provider.get(key, default='not-from-vault') == 'not-from-vault'


@pytest.mark.parametrize(
    'key', ['VAULT_ADDR', 'VAULT_TOKEN', 'VAULT_ROLE_ID', 'DJANGO_SETTINGS_MODULE']
)
def test_bootstrap_keys_never_take_the_vault_value(use_vault, key):
    """
    Reading Vault's own configuration from Vault would be circular.

    The environment value must win even under VAULT_PRECEDENCE=vault.
    """
    use_vault({key: 'vault-value'})
    provider = SecretProvider(
        env={
            'VAULT_ADDR': 'http://vault:8200',
            'VAULT_PRECEDENCE': 'vault',
            key: 'env-value',
        }
    )

    assert provider.get(key) == 'env-value'


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

def test_vault_outage_falls_back_when_not_required(use_vault):
    use_vault(fail=True)
    provider = SecretProvider(env={'VAULT_ADDR': 'http://vault:8200', 'DB_NAME': 'env-db'})

    assert provider.get('DB_NAME') == 'env-db'


def test_vault_outage_raises_when_required(use_vault):
    use_vault(fail=True)
    provider = SecretProvider(
        env={'VAULT_ADDR': 'http://vault:8200', 'VAULT_REQUIRED': 'true'}
    )

    with pytest.raises(VaultUnavailable):
        provider.get('DB_NAME', default='ignored')


def test_required_without_addr_raises():
    provider = SecretProvider(env={'VAULT_REQUIRED': 'true'})

    with pytest.raises(VaultUnavailable, match='VAULT_ADDR'):
        provider.get('ANYTHING', default='ignored')


# ---------------------------------------------------------------------------
# Diagnostics must never leak values
# ---------------------------------------------------------------------------

def test_describe_reports_counts_not_values(use_vault):
    use_vault({'SECRET_KEY': 'super-secret', 'DB_PASSWORD': 'also-secret'})
    provider = SecretProvider(env={'VAULT_ADDR': 'http://vault:8200'})

    summary = provider.describe()

    assert summary['vault_key_count'] == 2
    assert 'super-secret' not in str(summary)
    assert 'also-secret' not in str(summary)


def test_source_of_identifies_origin(use_vault):
    use_vault({'FROM_VAULT': 'v'})
    provider = SecretProvider(env={'VAULT_ADDR': 'http://vault:8200', 'FROM_ENV': 'e'})

    assert provider.source_of('FROM_ENV') == 'environment'
    assert provider.source_of('FROM_VAULT') == 'vault'
    assert provider.source_of('NOWHERE_AT_ALL_XYZ') == 'unset'


# ---------------------------------------------------------------------------
# dotenv parsing used by `manage.py vault_push`
# ---------------------------------------------------------------------------

def test_dotenv_parser_handles_real_world_lines(tmp_path):
    from api.management.commands.vault_push import parse_dotenv

    env_file = tmp_path / '.env'
    env_file.write_text(
        '\n'.join(
            [
                '# a comment',
                '',
                'PLAIN=value',
                'QUOTED="quoted value"',
                "SINGLE='single quoted'",
                'export EXPORTED=exported-value',
                'EMPTY=',
                'WITH_EQUALS=key=value=more',
                '   SPACED   =   trimmed   ',
                'not a valid line',
            ]
        ),
        encoding='utf-8',
    )

    parsed = parse_dotenv(env_file)

    assert parsed['PLAIN'] == 'value'
    assert parsed['QUOTED'] == 'quoted value'
    assert parsed['SINGLE'] == 'single quoted'
    assert parsed['EXPORTED'] == 'exported-value'
    assert parsed['EMPTY'] == ''
    assert parsed['WITH_EQUALS'] == 'key=value=more'
    assert parsed['SPACED'] == 'trimmed'
    assert 'not a valid line' not in parsed


def test_vault_push_excludes_bootstrap_keys():
    from api.management.commands.vault_push import EXCLUDED_KEYS

    for key in ('VAULT_ADDR', 'VAULT_TOKEN', 'VAULT_ROLE_ID', 'DJANGO_SETTINGS_MODULE', 'DEBUG'):
        assert key in EXCLUDED_KEYS, f'{key} must never be written into Vault'
