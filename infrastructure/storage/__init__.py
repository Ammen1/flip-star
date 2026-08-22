"""Object storage (S3 / MinIO) configuration."""

from infrastructure.storage.config import apply_storage_settings, is_object_storage_enabled

__all__ = ['apply_storage_settings', 'is_object_storage_enabled']
