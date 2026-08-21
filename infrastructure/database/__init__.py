"""Database connection resolution."""

from infrastructure.database.config import build_database_config, is_managed_host

__all__ = ['build_database_config', 'is_managed_host']
