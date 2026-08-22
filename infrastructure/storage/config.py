"""
Object storage (S3 / MinIO) resolution.

Media is stored in S3-compatible object storage when credentials are supplied,
and on the local filesystem otherwise. Static files are always served by
WhiteNoise regardless of the media backend.

Known deployment hazard (audit finding H-06): ``env.production.example``
documented ``AWS_``-prefixed variable names while the code read unprefixed
ones, so an operator following the documented procedure silently got local
storage. Both spellings are now accepted, unprefixed taking precedence.
"""

from __future__ import annotations

from typing import Any

from infrastructure.secrets import secret as config

FILESYSTEM_STORAGE = 'django.core.files.storage.FileSystemStorage'
S3_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
WHITENOISE_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


def _either(primary: str, fallback: str, default: str = '') -> str:
    """Read ``primary``, falling back to the legacy ``AWS_``-prefixed name."""
    return config(primary, default='') or config(fallback, default=default)


def apply_storage_settings(media_url: str) -> dict[str, Any]:
    """
    Resolve storage configuration.

    Returns a mapping the settings module unpacks into module-level names.
    ``media_url`` is the filesystem default, returned unchanged when object
    storage is not configured.
    """
    access_key_id = _either('ACCESS_KEY_ID', 'AWS_ACCESS_KEY_ID')
    secret_access_key = _either('SECRET_ACCESS_KEY', 'AWS_SECRET_ACCESS_KEY')
    bucket_name = _either('STORAGE_BUCKET_NAME', 'AWS_STORAGE_BUCKET_NAME')
    region_name = _either('REGION_NAME', 'AWS_S3_REGION_NAME', default='us-east-1')
    endpoint_url = _either('S3_ENDPOINT_URL', 'AWS_S3_ENDPOINT_URL')

    custom_domain = f'{bucket_name}.s3.amazonaws.com' if bucket_name else None

    # Uploaded media must be publicly readable (profile photos, reel media) --
    # without an explicit ACL, django-storages sends none at all, so an
    # object's readability falls back to the bucket's own default, which is
    # private on most providers. Configurable rather than hardcoded: a bucket
    # with S3 "Bucket owner enforced" Object Ownership rejects ACL headers
    # outright, so an operator on such a bucket needs to unset this via
    # S3_DEFAULT_ACL= (empty) rather than have every upload fail.
    default_acl = config('S3_DEFAULT_ACL', default='public-read') or None

    resolved: dict[str, Any] = {
        'access_key_id': access_key_id,
        'secret_access_key': secret_access_key,
        'bucket_name': bucket_name,
        'region_name': region_name,
        'endpoint_url': endpoint_url,
        'custom_domain': custom_domain,
        'staticfiles_storage': WHITENOISE_STORAGE,
        'use_ssl': False,
        'media_url': media_url,
        'default_acl': default_acl,
    }

    if not (access_key_id and secret_access_key and bucket_name):
        resolved['default_file_storage'] = FILESYSTEM_STORAGE
        return resolved

    resolved['default_file_storage'] = S3_STORAGE

    if endpoint_url:
        # Self-hosted MinIO.
        resolved['media_url'] = f'{endpoint_url}/{bucket_name}/media/'
        resolved['use_ssl'] = config('S3_USE_SSL', default=False, cast=bool)
    else:
        # AWS S3.
        resolved['media_url'] = f'https://{custom_domain}/media/'

    return resolved


def is_object_storage_enabled() -> bool:
    """True when S3/MinIO credentials are fully configured."""
    return bool(
        _either('ACCESS_KEY_ID', 'AWS_ACCESS_KEY_ID')
        and _either('SECRET_ACCESS_KEY', 'AWS_SECRET_ACCESS_KEY')
        and _either('STORAGE_BUCKET_NAME', 'AWS_STORAGE_BUCKET_NAME')
    )
