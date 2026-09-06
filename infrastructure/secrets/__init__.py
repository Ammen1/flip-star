"""
Secret resolution: HashiCorp Vault, with the environment and .env as fallbacks.

Settings modules import ``secret`` in place of ``decouple.config``. The
signature is identical, so the swap is a single import line per module::

    from infrastructure.secrets import secret as config

Vault is optional. With ``VAULT_ADDR`` unset, resolution behaves exactly as it
did before Vault was introduced. See ``docs/secrets.md``.
"""

from infrastructure.secrets.provider import (
    NO_DOTENV,
    UNSET,
    SecretProvider,
    default_provider,
    secret,
)
from infrastructure.secrets.vault import VaultClient, VaultUnavailable

__all__ = [
    'NO_DOTENV',
    'UNSET',
    'SecretProvider',
    'VaultClient',
    'VaultUnavailable',
    'default_provider',
    'secret',
]
