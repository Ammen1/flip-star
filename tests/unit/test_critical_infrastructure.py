"""
Tests for infrastructure/health/startup.py -- the independent Redis/Vault
startup check.

Each dependency is checked on its own: an unreachable Redis is fatal even
when Vault is fine, and a configured-but-unreachable Vault is fatal even
when Redis is fine. Neither escape hatch changed -- Vault unconfigured
(``VAULT_ADDR`` unset) and Redis not being the cache backend (e.g.
``USE_LOCMEM_CACHE=true``) both still mean "not required", not "down".
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from infrastructure.health.startup import (
    CriticalInfrastructureUnavailable,
    _redis_status,
    _vault_status,
    verify_redis_and_vault,
)

pytestmark = pytest.mark.unit

_MODULE = 'infrastructure.health.startup'


# ---------------------------------------------------------------------------
# _redis_status
# ---------------------------------------------------------------------------

def test_locmem_cache_has_no_redis_dependency(settings):
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    ok, _detail = _redis_status()
    assert ok is True


def test_redis_cache_ok_when_it_answers(settings):
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache'}}
    fake_cache = MagicMock()
    fake_cache.get.return_value = '1'
    with patch('django.core.cache.cache', fake_cache):
        ok, _detail = _redis_status()
        assert ok is True


def test_redis_cache_not_ok_when_it_raises(settings):
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache'}}
    fake_cache = MagicMock()
    fake_cache.set.side_effect = ConnectionError('refused')
    with patch('django.core.cache.cache', fake_cache):
        ok, detail = _redis_status()
        assert ok is False
        assert 'unreachable' in detail


def test_redis_cache_not_ok_when_roundtrip_value_mismatches(settings):
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache'}}
    fake_cache = MagicMock()
    fake_cache.get.return_value = None  # e.g. wrote to one node, read a stale miss elsewhere
    with patch('django.core.cache.cache', fake_cache):
        ok, detail = _redis_status()
        assert ok is False
        assert 'round-trip' in detail


# ---------------------------------------------------------------------------
# _vault_status
# ---------------------------------------------------------------------------

def test_vault_ok_when_not_configured():
    """VAULT_ADDR unset is a supported mode, not a failure -- see module docstring."""
    with patch('infrastructure.secrets.provider.default_provider') as provider:
        provider.vault_enabled = False
        ok, _detail = _vault_status()
        assert ok is True


def test_vault_not_ok_when_client_construction_fails():
    with patch('infrastructure.secrets.provider.default_provider') as provider, \
         patch('infrastructure.secrets.vault.VaultClient') as vault_client_cls:
        provider.vault_enabled = True
        vault_client_cls.from_env.return_value = None
        ok, _detail = _vault_status()
        assert ok is False


def test_vault_not_ok_when_health_check_raises():
    with patch('infrastructure.secrets.provider.default_provider') as provider, \
         patch('infrastructure.secrets.vault.VaultClient') as vault_client_cls:
        provider.vault_enabled = True
        client = MagicMock()
        client.health.side_effect = RuntimeError('connection refused')
        vault_client_cls.from_env.return_value = client
        ok, _detail = _vault_status()
        assert ok is False


def test_vault_not_ok_when_not_authenticated():
    with patch('infrastructure.secrets.provider.default_provider') as provider, \
         patch('infrastructure.secrets.vault.VaultClient') as vault_client_cls:
        provider.vault_enabled = True
        client = MagicMock()
        client.health.return_value = {'authenticated': False}
        vault_client_cls.from_env.return_value = client
        ok, _detail = _vault_status()
        assert ok is False


def test_vault_ok_when_healthy_and_authenticated():
    with patch('infrastructure.secrets.provider.default_provider') as provider, \
         patch('infrastructure.secrets.vault.VaultClient') as vault_client_cls:
        provider.vault_enabled = True
        client = MagicMock()
        client.health.return_value = {'authenticated': True, 'auth_method': 'approle'}
        vault_client_cls.from_env.return_value = client
        ok, _detail = _vault_status()
        assert ok is True


# ---------------------------------------------------------------------------
# verify_redis_and_vault -- each dependency gates independently
# ---------------------------------------------------------------------------

def test_passes_when_both_are_ok():
    with patch(f'{_MODULE}._redis_status', return_value=(True, 'reachable')), \
         patch(f'{_MODULE}._vault_status', return_value=(True, 'reachable and authenticated')):
        verify_redis_and_vault()  # must not raise


def test_raises_when_only_redis_is_down():
    with patch(f'{_MODULE}._redis_status', return_value=(False, 'unreachable (refused)')), \
         patch(f'{_MODULE}._vault_status', return_value=(True, 'reachable and authenticated')):
        with pytest.raises(CriticalInfrastructureUnavailable, match='Redis'):
            verify_redis_and_vault()


def test_raises_when_only_vault_is_down():
    with patch(f'{_MODULE}._redis_status', return_value=(True, 'reachable')), \
         patch(f'{_MODULE}._vault_status', return_value=(False, 'unreachable (refused)')):
        with pytest.raises(CriticalInfrastructureUnavailable, match='Vault'):
            verify_redis_and_vault()


def test_raises_when_both_are_down():
    with patch(f'{_MODULE}._redis_status', return_value=(False, 'unreachable')), \
         patch(f'{_MODULE}._vault_status', return_value=(False, 'unreachable')):
        with pytest.raises(CriticalInfrastructureUnavailable, match='Redis.*Vault|Vault.*Redis'):
            verify_redis_and_vault()


def test_passes_when_neither_is_configured():
    """LocMem cache + no VAULT_ADDR -- the standard local-dev mode -- must still boot."""
    with patch(f'{_MODULE}._redis_status', return_value=(True, 'not configured as the cache backend, so not required')), \
         patch(f'{_MODULE}._vault_status', return_value=(True, 'not configured (VAULT_ADDR unset), so not required')):
        verify_redis_and_vault()  # must not raise
