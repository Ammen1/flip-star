"""
HashiCorp Vault client.

Reads a KV v2 secret path once at startup and caches the result. Settings
resolve ~55 values; issuing one API call per value would make every process
start slowly and fail unpredictably, so the whole path is fetched in a single
read and served from memory.

Authentication, in order of preference:

* **AppRole** (``VAULT_ROLE_ID`` + ``VAULT_SECRET_ID``) -- the production method.
* **Token** (``VAULT_TOKEN``) -- development and the Vault dev server.

The client never raises during normal settings resolution. If Vault is
unreachable it logs and returns nothing, letting the provider fall through to
the environment. ``VAULT_REQUIRED=true`` turns that into a hard failure, which
is what production should set once Vault is the source of truth.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

#: Seconds to wait for Vault. Deliberately short -- this runs during settings
#: import, and a hung secret store must not hang the container indefinitely.
DEFAULT_TIMEOUT = 5

#: Default KV v2 mount point.
DEFAULT_MOUNT = 'secret'

#: Default path within the mount holding the backend's secrets.
DEFAULT_PATH = 'flipstar/backend'


class VaultUnavailable(RuntimeError):
    """Vault was required but could not be reached or authenticated."""


class VaultClient:
    """Thin wrapper over ``hvac`` that batch-reads one KV v2 path."""

    def __init__(
        self,
        addr: str,
        *,
        mount_point: str = DEFAULT_MOUNT,
        path: str = DEFAULT_PATH,
        token: str | None = None,
        role_id: str | None = None,
        secret_id: str | None = None,
        namespace: str | None = None,
        verify: bool | str = True,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.addr = addr.rstrip('/')
        self.mount_point = mount_point
        self.path = path
        self.token = token
        self.role_id = role_id
        self.secret_id = secret_id
        self.namespace = namespace
        self.verify = verify
        self.timeout = timeout

        self._client: Any | None = None
        self._loaded = False
        self._secrets: dict[str, str] = {}

    # -- construction --------------------------------------------------------

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> VaultClient | None:
        """
        Build a client from environment variables, or return ``None``.

        ``None`` means "Vault is not configured" -- not an error. The provider
        treats that as a signal to use the environment and .env only, which is
        exactly the behaviour this project had before Vault existed.
        """
        env = env if env is not None else dict(os.environ)

        addr = env.get('VAULT_ADDR', '').strip()
        if not addr:
            return None

        verify_raw = env.get('VAULT_SKIP_VERIFY', '').strip().lower()
        verify: bool | str
        if verify_raw in ('1', 'true', 'yes'):
            verify = False
        else:
            verify = env.get('VAULT_CACERT', '').strip() or True

        return cls(
            addr=addr,
            mount_point=env.get('VAULT_KV_MOUNT', DEFAULT_MOUNT).strip() or DEFAULT_MOUNT,
            path=env.get('VAULT_SECRET_PATH', DEFAULT_PATH).strip() or DEFAULT_PATH,
            token=env.get('VAULT_TOKEN', '').strip() or None,
            role_id=env.get('VAULT_ROLE_ID', '').strip() or None,
            secret_id=env.get('VAULT_SECRET_ID', '').strip() or None,
            namespace=env.get('VAULT_NAMESPACE', '').strip() or None,
            verify=verify,
            timeout=int(env.get('VAULT_TIMEOUT', DEFAULT_TIMEOUT)),
        )

    # -- connection ----------------------------------------------------------

    def _connect(self) -> Any:
        """Return an authenticated hvac client. Raises on failure."""
        if self._client is not None:
            return self._client

        try:
            import hvac
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise VaultUnavailable(
                'VAULT_ADDR is set but the hvac package is not installed. '
                'Add hvac to requirements.txt or unset VAULT_ADDR.'
            ) from exc

        client = hvac.Client(
            url=self.addr,
            namespace=self.namespace,
            verify=self.verify,
            timeout=self.timeout,
        )

        # AppRole first: it is the only method suitable for production, because
        # the secret_id can be response-wrapped and rotated independently.
        if self.role_id and self.secret_id:
            response = client.auth.approle.login(
                role_id=self.role_id,
                secret_id=self.secret_id,
            )
            client.token = response['auth']['client_token']
            logger.info('Authenticated to Vault via AppRole', extra={'provider': 'vault'})
        elif self.token:
            client.token = self.token
            logger.info('Authenticated to Vault via token', extra={'provider': 'vault'})
        else:
            raise VaultUnavailable(
                'VAULT_ADDR is set but no credentials were supplied. '
                'Provide VAULT_ROLE_ID + VAULT_SECRET_ID, or VAULT_TOKEN.'
            )

        if not client.is_authenticated():
            raise VaultUnavailable('Vault rejected the supplied credentials.')

        self._client = client
        return client

    # -- reads ---------------------------------------------------------------

    def load(self) -> dict[str, str]:
        """
        Fetch the secret path once and cache it.

        Returns an empty mapping when Vault is unreachable, so callers can fall
        through. Use :meth:`load_or_raise` when absence must be fatal.
        """
        if self._loaded:
            return self._secrets

        try:
            self._secrets = self._read()
        except Exception as exc:
            logger.warning(
                'Vault read failed, falling back to environment: %s',
                exc,
                extra={'provider': 'vault', 'result': 'unavailable'},
            )
            self._secrets = {}
        finally:
            self._loaded = True

        return self._secrets

    def load_or_raise(self) -> dict[str, str]:
        """Fetch the secret path, raising :class:`VaultUnavailable` on failure."""
        if self._loaded and self._secrets:
            return self._secrets

        try:
            self._secrets = self._read()
        except VaultUnavailable:
            raise
        except Exception as exc:
            raise VaultUnavailable(f'Could not read secrets from Vault: {exc}') from exc
        finally:
            self._loaded = True

        return self._secrets

    def _read(self) -> dict[str, str]:
        client = self._connect()

        try:
            response = client.secrets.kv.v2.read_secret_version(
                path=self.path,
                mount_point=self.mount_point,
                raise_on_deleted_version=True,
            )
        except Exception as exc:
            # A path that does not exist yet is the normal state before the
            # first `vault_push`, not a failure. Reporting it as an error sends
            # operators looking for a connectivity problem that isn't there.
            if type(exc).__name__ == 'InvalidPath':
                logger.info(
                    'Vault path %s/%s does not exist yet; no secrets loaded.',
                    self.mount_point,
                    self.path,
                    extra={'provider': 'vault', 'result': 'empty'},
                )
                return {}
            raise

        data = response['data']['data']

        # Vault values may be non-string (numbers, booleans) if written via the
        # API. Settings resolution expects strings, matching os.environ.
        secrets = {str(key): '' if value is None else str(value) for key, value in data.items()}

        logger.info(
            'Loaded %d secrets from Vault at %s/%s',
            len(secrets),
            self.mount_point,
            self.path,
            extra={'provider': 'vault', 'result': 'ok'},
        )
        return secrets

    # -- writes (used by management commands, never at runtime) --------------

    def write(self, secrets: dict[str, str]) -> None:
        """Replace the secret path's contents. Used by ``manage.py vault_push``."""
        client = self._connect()
        client.secrets.kv.v2.create_or_update_secret(
            path=self.path,
            secret=secrets,
            mount_point=self.mount_point,
        )
        self._loaded = False
        self._secrets = {}

    def health(self) -> dict[str, Any]:
        """Return connectivity details for ``manage.py vault_status``."""
        client = self._connect()
        return {
            'addr': self.addr,
            'authenticated': client.is_authenticated(),
            'mount_point': self.mount_point,
            'path': self.path,
            'auth_method': 'approle' if (self.role_id and self.secret_id) else 'token',
        }
