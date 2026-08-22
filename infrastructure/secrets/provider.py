"""
Secret resolution.

``secret()`` is a drop-in replacement for ``decouple.config`` -- same signature,
same casting behaviour -- so migrating the settings modules is an import swap
rather than 55 individual edits.

Resolution order, first hit wins:

1. **OS environment** -- an operator override and the break-glass path. Also how
   ``docker compose`` and CI inject values.
2. **Vault** -- the source of truth for secrets once populated.
3. **.env file** (via python-decouple) -- local development.
4. **default** -- as passed by the caller.

Environment deliberately outranks Vault so a running deployment can be corrected
without a Vault write. Set ``VAULT_PRECEDENCE=vault`` to invert 1 and 2 where
Vault must be authoritative.

When ``VAULT_ADDR`` is unset the Vault step is skipped entirely and behaviour is
identical to this project before Vault existed.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from decouple import UndefinedValueError
from decouple import config as dotenv_config

from infrastructure.secrets.vault import VaultClient, VaultUnavailable

logger = logging.getLogger(__name__)

#: Sentinel distinguishing "no default supplied" from "default is None".
UNSET: Any = object()

#: Variables that configure Vault itself. Reading them from Vault would be
#: circular, so they always resolve from the environment only.
BOOTSTRAP_KEYS = frozenset(
    {
        'VAULT_ADDR',
        'VAULT_TOKEN',
        'VAULT_ROLE_ID',
        'VAULT_SECRET_ID',
        'VAULT_NAMESPACE',
        'VAULT_KV_MOUNT',
        'VAULT_SECRET_PATH',
        'VAULT_CACERT',
        'VAULT_SKIP_VERIFY',
        'VAULT_TIMEOUT',
        'VAULT_REQUIRED',
        'VAULT_PRECEDENCE',
        'DJANGO_ENV',
        'DJANGO_SETTINGS_MODULE',
    }
)

_TRUE = {'1', 'true', 'yes', 'on', 't', 'y'}
_FALSE = {'0', 'false', 'no', 'off', 'f', 'n', ''}


def _as_bool(value: Any) -> bool:
    """Match decouple's boolean casting so `cast=bool` behaves identically."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError(f'Cannot cast {value!r} to bool')


class SecretProvider:
    """Resolves configuration values across the environment, Vault and .env."""

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self._env = env if env is not None else os.environ
        self._vault: VaultClient | None = None
        self._vault_secrets: dict[str, str] | None = None
        self._vault_initialised = False

    # -- Vault wiring --------------------------------------------------------

    @property
    def vault_required(self) -> bool:
        return _as_bool(self._env.get('VAULT_REQUIRED', 'false'))

    @property
    def vault_first(self) -> bool:
        return self._env.get('VAULT_PRECEDENCE', 'env').strip().lower() == 'vault'

    @property
    def vault_enabled(self) -> bool:
        return bool(self._env.get('VAULT_ADDR', '').strip())

    def _vault_values(self) -> dict[str, str]:
        """Load and memoise the Vault payload. Empty when Vault is off."""
        if self._vault_initialised:
            return self._vault_secrets or {}

        self._vault_initialised = True

        if not self.vault_enabled:
            if self.vault_required:
                raise VaultUnavailable('VAULT_REQUIRED=true but VAULT_ADDR is not set.')
            self._vault_secrets = {}
            return {}

        self._vault = VaultClient.from_env(dict(self._env))
        if self._vault is None:  # pragma: no cover - guarded by vault_enabled
            self._vault_secrets = {}
            return {}

        if self.vault_required:
            self._vault_secrets = self._vault.load_or_raise()
        else:
            self._vault_secrets = self._vault.load()

        return self._vault_secrets

    # -- resolution ----------------------------------------------------------

    def _lookup(self, key: str) -> tuple[bool, Any]:
        """Return ``(found, value)`` following the configured precedence."""
        if key in BOOTSTRAP_KEYS:
            if key in self._env:
                return True, self._env[key]
            return False, None

        sources: list[Callable[[], tuple[bool, Any]]] = [
            lambda: (key in self._env, self._env.get(key)),
            lambda: (key in self._vault_values(), self._vault_values().get(key)),
        ]
        if self.vault_first:
            sources.reverse()

        for source in sources:
            found, value = source()
            if found:
                return True, value

        # .env file, via decouple. UndefinedValueError means "not present".
        try:
            return True, dotenv_config(key)
        except UndefinedValueError:
            return False, None

    def get(self, key: str, default: Any = UNSET, cast: Any = UNSET) -> Any:
        """
        Resolve ``key``.

        Mirrors ``decouple.config``: raises when a value is absent and no
        default was supplied, and applies ``cast`` to whatever is found.
        """
        found, value = self._lookup(key)

        if not found:
            if default is UNSET:
                raise UndefinedValueError(
                    f'{key} not found. Set it in the environment, in Vault '
                    f'({self._env.get("VAULT_SECRET_PATH", "flipstar/backend")}), '
                    'or in the .env file.'
                )
            value = default

        if cast is UNSET or value is None:
            return value

        if cast is bool:
            return _as_bool(value)

        try:
            return cast(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'Cannot cast {key}={value!r} using {cast!r}: {exc}') from exc

    # -- diagnostics ---------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        """Summarise the active configuration. Never returns secret values."""
        return {
            'vault_enabled': self.vault_enabled,
            'vault_required': self.vault_required,
            'precedence': 'vault' if self.vault_first else 'env',
            'vault_addr': self._env.get('VAULT_ADDR', '') or None,
            'vault_path': self._env.get('VAULT_SECRET_PATH', 'flipstar/backend'),
            'vault_key_count': len(self._vault_values()) if self.vault_enabled else 0,
        }

    def source_of(self, key: str) -> str:
        """Report which source supplies ``key``. For diagnostics only."""
        if key in BOOTSTRAP_KEYS:
            return 'environment' if key in self._env else 'unset'
        in_env = key in self._env
        in_vault = key in self._vault_values()

        if self.vault_first:
            if in_vault:
                return 'vault'
            if in_env:
                return 'environment'
        else:
            if in_env:
                return 'environment'
            if in_vault:
                return 'vault'

        try:
            dotenv_config(key)
            return 'dotenv'
        except UndefinedValueError:
            return 'unset'


#: Process-wide provider. Settings import this once; the Vault payload is
#: fetched at most once per process.
#:
#: Named ``default_provider`` rather than ``provider`` so it does not shadow this
#: module inside the package namespace -- ``infrastructure.secrets.provider``
#: must keep resolving to the module for patching and introspection.
default_provider = SecretProvider()


def secret(key: str, default: Any = UNSET, cast: Any = UNSET) -> Any:
    """Drop-in replacement for ``decouple.config``."""
    return default_provider.get(key, default=default, cast=cast)
