"""
Centralized runtime configuration -- NOT the path this application uses.

.. warning::

   Audit finding L-08. Nothing outside this package imports it; the whole
   package is at 0% test coverage. FlipStar resolves configuration through::

       config/settings/base.py:20
       from infrastructure.secrets import secret as config

   and that module defaults to environment variables **overriding** Vault
   (``VAULT_PRECEDENCE`` defaults to ``'env'``), which is the opposite of what
   this package's own docstrings used to claim. See ``loader.py`` for the full
   note.

   ``schema.py`` is still cited as documentation of the recognised configuration
   keys (``config/settings/base.py:307``, ``:753``), which is why this package
   was annotated rather than removed.

What follows describes this package's intended interface, which no deployment
exercises.

    from infrastructure.config import get_config
    cfg = get_config()
    cfg.require('DB_HOST')      # aborts if absent
    cfg.get('TELEBIRR_APP_SECRET')   # optional, may be None

In this design Vault is the only source. See loader.py for the bootstrap
variables that necessarily remain in the environment, and schema.py for every
key the application recognises.
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
