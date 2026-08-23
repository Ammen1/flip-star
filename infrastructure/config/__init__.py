"""
Centralized runtime configuration.

    from infrastructure.config import get_config
    cfg = get_config()
    cfg.require('DB_HOST')      # aborts if absent
    cfg.get('TELEBIRR_APP_SECRET')   # optional, may be None

Vault is the only source. See loader.py for the bootstrap variables that
necessarily remain in the environment, and schema.py for every key the
application recognises.
"""

from infrastructure.config.exceptions import (
    ConfigurationError,
    InvalidConfiguration,
    MissingConfiguration,
    VaultUnreachable,
)
from infrastructure.config.loader import (
    BOOTSTRAP,
    RuntimeConfig,
    get_config,
    load,
    reset_cache,
)
from infrastructure.config.schema import BY_NAME, GROUPS, REQUIRED, SCHEMA

__all__ = [
    'BOOTSTRAP',
    'BY_NAME',
    'ConfigurationError',
    'GROUPS',
    'InvalidConfiguration',
    'MissingConfiguration',
    'REQUIRED',
    'RuntimeConfig',
    'SCHEMA',
    'VaultUnreachable',
    'get_config',
    'load',
    'reset_cache',
]
