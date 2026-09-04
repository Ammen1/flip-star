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

    # The public host media is served from. Derived from the endpoint when one
    # is set: hardcoding the AWS form produced `<bucket>.s3.amazonaws.com` for
    # an Ethio Telecom OBS deployment, a domain that does not exist. That value
    # is what SecurityHeadersMiddleware puts in the CSP img-src/media-src
    # allowlist, so every real media URL was outside the policy and the browser
    # refused to load it -- posts rendered with an empty frame and no error.
    if endpoint_url:
        custom_domain = endpoint_url.split('://', 1)[-1].rstrip('/')
    elif bucket_name:
        custom_domain = f'{bucket_name}.s3.amazonaws.com'
    else:
        custom_domain = None

    # Uploaded media must be publicly readable (profile photos, reel media) --
    # without an explicit ACL, django-storages sends none at all, so an
    # object's readability falls back to the bucket's own default, which is
    # private on most providers. Configurable rather than hardcoded: a bucket
    # with S3 "Bucket owner enforced" Object Ownership rejects ACL headers
    # outright, so an operator on such a bucket needs to unset this via
    # S3_DEFAULT_ACL= (empty) rather than have every upload fail.
    default_acl = config('S3_DEFAULT_ACL', default='public-read') or None

    # Sign every media URL, or serve stable ones?
    #
    # django-storages defaults this to True, which presigns every URL with a
    # fresh X-Amz-Date and X-Amz-Signature. For a feed that is pathological:
    # each API response hands the browser a DIFFERENT url for the same object,
    # so the cache key changes every time and nothing is ever reused. Scrolling
    # back re-downloads an image already on disk, and a CDN can never hold an
    # edge copy. The signatures also expire (an hour by default), so a page
    # left open long enough starts answering 403.
    #
    # Signing buys nothing while default_acl is public-read: the unsigned URL
    # serves the same bytes to anyone who asks. So it defaults off exactly when
    # the objects are public, and stays on when they are not -- a private
    # bucket still needs signatures, and the cost of re-downloading is the
    # correct price for access control.
    #
    # Override with S3_QUERYSTRING_AUTH when the two need to be decoupled.
    querystring_auth = config(
        'S3_QUERYSTRING_AUTH',
        default=(default_acl != 'public-read'),
        cast=bool,
    )

    # Cache-Control written onto uploaded objects. Media is immutable: the key
    # contains the upload's own name, and processing writes to a new key rather
    # than overwriting, so a stored copy never goes stale. Without this header
    # the browser revalidates on every view even when the URL is stable.
    object_parameters = {
        'CacheControl': config(
            'S3_CACHE_CONTROL', default='public, max-age=31536000, immutable'
        ),
    }

    resolved: dict[str, Any] = {
        'access_key_id': access_key_id,
        'secret_access_key': secret_access_key,
        'bucket_name': bucket_name,
        'region_name': region_name,
        'endpoint_url': endpoint_url,
        'custom_domain': custom_domain,
        'staticfiles_storage': WHITENOISE_STORAGE,
        'use_ssl': False,
        'querystring_auth': querystring_auth,
        'object_parameters': object_parameters,
        'media_url': media_url,
        'default_acl': default_acl,
    }

    if not (access_key_id and secret_access_key and bucket_name):
        resolved['default_file_storage'] = FILESYSTEM_STORAGE
        return resolved

    resolved['default_file_storage'] = S3_STORAGE

    if endpoint_url:
        # Self-hosted MinIO, or a provider's S3-compatible endpoint.
        resolved['media_url'] = f'{endpoint_url}/{bucket_name}/media/'
        # Defaults on. An http:// endpoint puts every media URL outside the
        # CSP's img-src/media-src, which permit the https: scheme only, so the
        # browser blocks them before a request is made. It also sends the
        # access key and signature in clear over the network.
        resolved['use_ssl'] = config('S3_USE_SSL', default=True, cast=bool)
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
