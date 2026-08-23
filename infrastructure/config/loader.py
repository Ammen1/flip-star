"""
Load runtime configuration from Vault, validate it, or abort startup.

    Vault -> VaultClient -> load() -> validate against schema -> RuntimeConfig

There is deliberately no environment fallback and no default for anything the
schema marks required. A missing value stops the process with a message naming
the path and key. The alternative -- starting with a plausible default -- is
how an application ends up talking to the wrong database while appearing
healthy, which is strictly worse than not starting.

Bootstrap
---------
Five values must come from the environment, because reading Vault's address
out of Vault is circular:

    VAULT_ADDR         where Vault is
    VAULT_ROLE_ID      AppRole auth  (or VAULT_TOKEN)
    VAULT_SECRET_ID    AppRole auth  (or VAULT_TOKEN)
    VAULT_SECRET_PATH  which environment's configuration to read
    VAULT_KV_MOUNT     which KV mount it lives on

They are credentials for Vault and a pointer at an environment -- not
application configuration. Everything else comes from Vault.

Environment separation
----------------------
VAULT_SECRET_PATH is required and has no default. A staging deployment that
forgets to set it does not silently read production configuration; it fails to
start. That is the point.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from infrastructure.config.exceptions import (
    ConfigurationError,
    InvalidConfiguration,
    MissingConfiguration,
    VaultUnreachable,
)
from infrastructure.config.schema import BY_NAME, CASTS, GROUPS, SCHEMA

logger = logging.getLogger(__name__)

#: Environment variables that legitimately live outside Vault.
BOOTSTRAP = (
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
    'DJANGO_SETTINGS_MODULE',
    'DJANGO_ENV',
)


class RuntimeConfig:
    """
    Validated configuration. Read-only, and it never reveals a value in a
    repr, a log line, or a traceback.
    """

    __slots__ = ('_values', '_path', '_missing_groups')

    def __init__(self, values: dict[str, Any], path: str, missing_groups: tuple[str, ...]):
        self._values = values
        self._path = path
        self._missing_groups = missing_groups

    @property
    def vault_path(self) -> str:
        return self._path

    @property
    def unconfigured_groups(self) -> tuple[str, ...]:
        """Optional feature groups with no values set. Reported at startup."""
        return self._missing_groups

    def __contains__(self, name: str) -> bool:
        return name in self._values

    def require(self, name: str) -> Any:
        """
        Fetch a value that must exist. Raises rather than returning a default.

        Use this for anything the calling code cannot proceed without, even if
        the schema marks it optional -- an integration reading its own
        credentials should fail loudly at the point of use.
        """
        if name not in self._values:
            raise MissingConfiguration(
                'Required configuration missing.\n'
                f'  Path: {self._path}\n'
                f'  Key:  {name}\n'
                'Add it to Vault and restart.',
                path=self._path,
                key=name,
            )
        return self._values[name]

    def get(self, name: str, default: Any = None) -> Any:
        """
        Fetch an optional value.

        Only legitimate for schema-optional keys. Reaching for this on a
        required key is a bug, so it raises instead of quietly obliging.
        """
        key = BY_NAME.get(name)
        if key is not None and key.required:
            raise InvalidConfiguration(
                f'get() called for {name!r}, which the schema marks required. '
                'Use require() -- a required key must never resolve to a default.'
            )
        return self._values.get(name, default)

    def has_group(self, group: str) -> bool:
        """True when every key in an optional group has a value."""
        keys = GROUPS.get(group, ())
        return bool(keys) and all(k.name in self._values for k in keys)

    def __repr__(self) -> str:
        return '<RuntimeConfig path=%s keys=%d>' % (self._path, len(self._values))

    __str__ = __repr__


def _bootstrap_env(env: dict[str, str]) -> tuple[str, str]:
    """Validate the environment carries enough to reach Vault at all."""
    addr = (env.get('VAULT_ADDR') or '').strip()
    if not addr:
        raise VaultUnreachable(
            'VAULT_ADDR is not set.\n'
            'This application reads all runtime configuration from Vault and has '
            'no environment or file fallback. Set VAULT_ADDR, VAULT_SECRET_PATH '
            'and either VAULT_TOKEN or VAULT_ROLE_ID + VAULT_SECRET_ID.'
        )

    path = (env.get('VAULT_SECRET_PATH') or '').strip()
    if not path:
        raise VaultUnreachable(
            'VAULT_SECRET_PATH is not set.\n'
            "It selects which environment's configuration to load, e.g. "
            '"flipstar/backend/staging". There is deliberately no default: a '
            'deployment that omits it must fail rather than risk reading '
            "another environment's configuration."
        )

    has_token = bool((env.get('VAULT_TOKEN') or '').strip())
    has_approle = bool(
        (env.get('VAULT_ROLE_ID') or '').strip() and (env.get('VAULT_SECRET_ID') or '').strip()
    )
    if not (has_token or has_approle):
        raise VaultUnreachable(
            'No Vault credentials in the environment.\n'
            'Set VAULT_TOKEN, or both VAULT_ROLE_ID and VAULT_SECRET_ID.'
        )
    return addr, path


def load(env: dict[str, str] | None = None) -> RuntimeConfig:
    """
    Build a validated RuntimeConfig, or raise ConfigurationError.

    Every failure mode aborts: no Vault address, bad credentials, missing
    path, missing required key, empty required value, uncastable value.
    """
    env = dict(os.environ) if env is None else dict(env)
    addr, path = _bootstrap_env(env)

    # imported here so `import loader` does not require hvac to be installed,
    # which keeps the testing settings module importable without it
    from infrastructure.secrets.vault import VaultClient, VaultUnavailable

    client = VaultClient.from_env(env)
    if client is None:
        raise VaultUnreachable(
            'Vault client could not be built from the environment.\n' f'  VAULT_ADDR: {addr}'
        )

    try:
        raw = client.load_or_raise()
    except VaultUnavailable as exc:
        raise VaultUnreachable(
            'Vault is unreachable or refused authentication. Startup aborted.\n'
            f'  Address: {addr}\n'
            f'  Path:    {path}\n'
            f'  Cause:   {exc}',
            path=path,
        ) from exc

    if not raw:
        raise MissingConfiguration(
            'Vault returned no data. The path is empty or does not exist.\n'
            f'  Path: {path}\n'
            'Startup aborted.',
            path=path,
        )

    return _validate(raw, path)


def _validate(raw: dict[str, str], path: str) -> RuntimeConfig:
    """Apply the schema: required present and non-empty, values castable."""
    values: dict[str, Any] = {}
    missing: list[str] = []
    empty: list[str] = []
    bad: list[str] = []

    for key in SCHEMA:
        if key.name not in raw:
            if key.required:
                missing.append(key.name)
            elif key.fallback is not None:
                values[key.name] = key.fallback
            continue

        rawval = raw[key.name]
        if rawval is None or str(rawval).strip() == '':
            if key.required:
                empty.append(key.name)
            continue

        try:
            values[key.name] = CASTS[key.kind](str(rawval).strip())
        except (TypeError, ValueError):
            # the value itself is never included -- only its name and type
            bad.append(f'{key.name} (expected {key.kind})')

    if missing or empty or bad:
        lines = ['Required Vault configuration is missing or unusable.', f'  Path: {path}']
        for name in sorted(missing):
            lines.append(f'  Key:  {name}   MISSING')
        for name in sorted(empty):
            lines.append(f'  Key:  {name}   EMPTY')
        for name in sorted(bad):
            lines.append(f'  Key:  {name}   NOT VALID')
        lines.append('Application startup aborted.')
        raise MissingConfiguration(
            '\n'.join(lines),
            path=path,
            key=(sorted(missing + empty)[0] if missing or empty else None),
        )

    unconfigured = tuple(
        sorted(g for g, keys in GROUPS.items() if keys and not any(k.name in values for k in keys))
    )

    logger.info(
        'Configuration loaded from Vault',
        extra={
            'vault_path': path,
            'keys': len(values),
            'unconfigured_groups': ','.join(unconfigured) or 'none',
        },
    )
    if unconfigured:
        logger.warning(
            'Optional feature groups have no configuration: %s. ' 'Those features will not work.',
            ', '.join(unconfigured),
        )

    return RuntimeConfig(values, path, unconfigured)


_cached: RuntimeConfig | None = None


def get_config(*, reload: bool = False) -> RuntimeConfig:
    """
    The process-wide configuration, loaded once.

    Settings modules call this at import. Everything else should read from
    django.conf.settings rather than calling this again -- one load per
    process keeps Vault off the request path.
    """
    global _cached
    if _cached is None or reload:
        _cached = load()
    return _cached


def reset_cache() -> None:
    """Test-only: forget the loaded configuration."""
    global _cached
    _cached = None


__all__ = [
    'BOOTSTRAP',
    'ConfigurationError',
    'InvalidConfiguration',
    'MissingConfiguration',
    'RuntimeConfig',
    'VaultUnreachable',
    'get_config',
    'load',
    'reset_cache',
]
