"""
Startup verification that critical infrastructure is actually *reachable*,
not just configured.

Redis and Vault each have a documented, legitimate way to run *unconfigured*:

* Vault is optional by design (see ``infrastructure/secrets``) -- with
  ``VAULT_ADDR`` unset, configuration resolves from the environment/.env
  exactly as it did before Vault existed. That is a supported mode, not a
  failure.
* Redis-for-cache has an explicit local-dev opt-out (``USE_LOCMEM_CACHE``,
  see ``config/settings/development.py``) that swaps in an in-process cache.
  With that set, the app has no Redis dependency to be unreachable.

What is *not* tolerated is a dependency that IS configured but does not
actually answer. If ``VAULT_ADDR`` is set, Vault is expected to work -- a
silent fallback to bare environment variables at that point would hide a
real outage. If the cache backend is Redis, it is expected to work -- OTP
delivery, rate limiting and the cache all silently degrade otherwise.
``verify_redis_and_vault()`` checks each dependency independently: an
unreachable Redis is fatal even if Vault is fine, and an unreachable (but
configured) Vault is fatal even if Redis is fine. It does not duplicate the
individual Redis or Vault handling that already exists elsewhere -- it only
adds the "configured but not actually working" boot-time gate.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_HEALTH_CHECK_CACHE_KEY = '__startup_health_check__'


class CriticalInfrastructureUnavailable(RuntimeError):
    pass


def _redis_status() -> tuple[bool, str]:
    """
    (ok, detail) for the cache-configured Redis dependency.

    ok=True when Redis isn't the configured cache backend at all (e.g.
    USE_LOCMEM_CACHE=true) -- there is nothing to be unreachable -- or when
    it is configured and a real set/get round-trip succeeds. ok=False only
    when Redis IS the configured backend and it does not answer correctly.
    """
    from django.conf import settings

    backend = settings.CACHES.get('default', {}).get('BACKEND', '')
    if 'redis' not in backend.lower():
        logger.info('Redis: not configured as the cache backend, so not required.')
        return True, 'not configured as the cache backend, so not required'

    from django.core.cache import cache

    try:
        cache.set(_HEALTH_CHECK_CACHE_KEY, '1', timeout=5)
    except Exception as exc:
        logger.error('Redis: unreachable (%s)', exc)
        return False, f'unreachable ({exc})'

    if cache.get(_HEALTH_CHECK_CACHE_KEY) != '1':
        logger.error('Redis: set/get round-trip failed (wrote a value, did not read it back).')
        return False, 'set/get round-trip failed (wrote a value, did not read it back)'

    logger.info('Redis: reachable.')
    return True, 'reachable'


def _vault_status() -> tuple[bool, str]:
    """
    (ok, detail) for the Vault dependency.

    ok=True when Vault isn't configured at all (VAULT_ADDR unset -- a
    supported mode, see module docstring) -- there is nothing to be
    unreachable -- or when it is configured, reachable, and authenticated.
    ok=False only when Vault IS configured (VAULT_ADDR set) and does not
    answer or does not authenticate.
    """
    from infrastructure.secrets.provider import default_provider
    from infrastructure.secrets.vault import VaultClient, VaultUnavailable

    if not default_provider.vault_enabled:
        return True, 'not configured (VAULT_ADDR unset), so not required'

    client = VaultClient.from_env()
    if client is None:
        return False, 'VAULT_ADDR is set but a client could not be constructed from the environment'

    try:
        health = client.health()
    except VaultUnavailable as exc:
        return False, f'unreachable ({exc})'
    except Exception as exc:
        return False, f'health check raised an unexpected error ({exc})'

    if not health.get('authenticated'):
        return False, 'reachable but not authenticated (check VAULT_TOKEN / auth method)'

    return True, 'reachable and authenticated'


def verify_redis_and_vault() -> None:
    """
    Raise :class:`CriticalInfrastructureUnavailable` if a dependency that IS
    configured -- Redis-for-cache or Vault -- cannot actually be reached.
    Each is checked independently, so either one failing on its own is
    enough to refuse startup; a dependency that simply isn't configured
    (``USE_LOCMEM_CACHE`` for Redis, unset ``VAULT_ADDR`` for Vault) is not
    "unreachable" and does not trip this check. Safe to call unconditionally
    at process startup.
    """
    redis_ok, redis_detail = _redis_status()
    vault_ok, vault_detail = _vault_status()

    if redis_ok and vault_ok:
        logger.debug('Startup infrastructure check passed -- Redis: %s; Vault: %s', redis_detail, vault_detail)
        return

    problems = []
    if not redis_ok:
        problems.append(f'Redis is {redis_detail}')
    if not vault_ok:
        logger.error('Vault unavailable at startup: %s', vault_detail)
        problems.append(f'Vault is {vault_detail}')

    message = 'Refusing to start -- required infrastructure is unreachable: ' + '; '.join(problems)
    logger.error(message)
    raise CriticalInfrastructureUnavailable(message)
