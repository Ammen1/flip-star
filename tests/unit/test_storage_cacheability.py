"""
Media URLs must be stable, cacheable, and inside the CSP.

Why the feed was slow
---------------------
Nothing was downloading whole videos up front -- the player already requests
`preload="none"` off screen and object storage honours Range. The cost was
elsewhere, and it was paid on every single render:

  rotating URLs   django-storages presigns by default. Every call to .url()
                  produced a fresh X-Amz-Date and X-Amz-Signature, so the same
                  object arrived under a different URL in every API response.
                  The browser cache is keyed on the URL, so nothing was ever
                  reused: scrolling back re-downloaded images already on disk,
                  and no CDN could hold an edge copy.

  wrong CSP host  custom_domain was hardcoded to `<bucket>.s3.amazonaws.com`
                  regardless of provider. That value goes into the CSP's
                  img-src/media-src allowlist, so on an Ethio Telecom OBS
                  deployment the allowlist named a domain that does not exist
                  while every real URL sat outside the policy.

  http endpoint   the CSP permits the https: scheme only, so plain-http media
                  is blocked before a request is made -- an empty frame, no
                  network entry, no console error a user would notice.

These pin the fixes. They exercise the resolver directly rather than a live
bucket, so they run anywhere.
"""

import pytest

from infrastructure.storage.config import apply_storage_settings

OBS_ENDPOINT = 'https://obsv3.et-global-3.ethiotelecom.et'


@pytest.fixture
def s3_env(monkeypatch):
    """Configure a provider endpoint the way staging is configured."""

    def _apply(**overrides):
        # Names as apply_storage_settings actually reads them: _either() looks
        # up the unprefixed form first, so it is STORAGE_BUCKET_NAME rather
        # than S3_BUCKET_NAME. Getting these wrong makes the resolver fall
        # through to the filesystem path and every assertion below meaningless.
        env = {
            'ACCESS_KEY_ID': 'test-key',
            'SECRET_ACCESS_KEY': 'test-secret',
            'STORAGE_BUCKET_NAME': 'flipstar',
            'S3_ENDPOINT_URL': OBS_ENDPOINT,
            'REGION_NAME': 'et-global-3',
        }
        env.update(overrides)
        for key, value in env.items():
            monkeypatch.setenv(key, str(value))
        return apply_storage_settings(media_url='/media/')

    return _apply


# ---------------------------------------------------------------------------
# Cacheability
# ---------------------------------------------------------------------------


def test_public_media_urls_are_not_signed(s3_env):
    """
    The cache fix.

    A signed URL carries a timestamp, so the same object is a cache miss every
    time it is served. Signing buys nothing while the objects are public-read
    -- the unsigned URL returns the same bytes to anyone who asks.
    """
    resolved = s3_env(S3_DEFAULT_ACL='public-read')

    assert resolved['querystring_auth'] is False


def test_private_media_is_still_signed(s3_env):
    """
    The security boundary the fix must not cross.

    A bucket that is not public still needs signatures. Re-downloading is the
    correct price for access control -- performance must never quietly turn
    private media public.
    """
    resolved = s3_env(S3_DEFAULT_ACL='private')

    assert resolved['querystring_auth'] is True


def test_signing_can_be_forced_independently(s3_env):
    """An operator can decouple the two when a bucket needs both."""
    resolved = s3_env(S3_DEFAULT_ACL='public-read', S3_QUERYSTRING_AUTH='true')

    assert resolved['querystring_auth'] is True


def test_uploads_carry_a_long_cache_lifetime(s3_env):
    """
    Media keys are immutable -- processing writes a new key rather than
    overwriting -- so a stored copy never goes stale and revalidation is
    wasted round trips on a mobile connection.
    """
    resolved = s3_env()
    cache_control = resolved['object_parameters']['CacheControl']

    assert 'public' in cache_control
    assert 'immutable' in cache_control
    assert 'max-age=31536000' in cache_control


def test_cache_control_is_configurable(s3_env):
    resolved = s3_env(S3_CACHE_CONTROL='public, max-age=60')

    assert resolved['object_parameters']['CacheControl'] == 'public, max-age=60'


# ---------------------------------------------------------------------------
# CSP alignment
# ---------------------------------------------------------------------------


def test_custom_domain_follows_the_endpoint(s3_env):
    """
    The blocked-media fix.

    custom_domain feeds SecurityHeadersMiddleware's img-src/media-src
    allowlist. Hardcoding the AWS form put a non-existent domain in the policy
    while every real URL fell outside it.
    """
    resolved = s3_env()

    assert resolved['custom_domain'] == 'obsv3.et-global-3.ethiotelecom.et'
    assert 'amazonaws' not in resolved['custom_domain']


def test_custom_domain_still_uses_the_aws_form_without_an_endpoint(s3_env):
    """Real AWS has no endpoint_url; that path must keep working."""
    resolved = s3_env(S3_ENDPOINT_URL='', AWS_S3_ENDPOINT_URL='')

    assert resolved['custom_domain'] == 'flipstar.s3.amazonaws.com'


def test_the_csp_allows_the_configured_media_host(settings):
    """
    End to end: whatever custom_domain resolves to must appear in the policy
    the middleware emits, or the browser blocks every image and video.
    """
    from common.middleware.security import SecurityHeadersMiddleware

    settings.S3_CUSTOM_DOMAIN = 'obsv3.et-global-3.ethiotelecom.et'
    policy = SecurityHeadersMiddleware(lambda r: None)._csp()

    assert 'obsv3.et-global-3.ethiotelecom.et' in policy
    for directive in ('img-src', 'media-src'):
        section = policy.split(f'{directive} ')[1].split(';')[0]
        assert 'obsv3.et-global-3.ethiotelecom.et' in section, f'missing from {directive}'


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


def test_ssl_is_on_by_default(s3_env):
    """
    Plain http media is blocked by our own CSP, which permits https: only --
    and it sends the access key and signature in clear.
    """
    resolved = s3_env()

    assert resolved['use_ssl'] is True


def test_ssl_can_be_disabled_for_a_local_minio(s3_env):
    resolved = s3_env(S3_USE_SSL='false')

    assert resolved['use_ssl'] is False


# ---------------------------------------------------------------------------
# The filesystem path must be unaffected
# ---------------------------------------------------------------------------


def test_incomplete_credentials_still_fall_back_to_local_storage(monkeypatch):
    """Nothing above may change the no-object-storage path."""
    for key in (
        'ACCESS_KEY_ID',
        'SECRET_ACCESS_KEY',
        'STORAGE_BUCKET_NAME',
        'AWS_ACCESS_KEY_ID',
        'AWS_SECRET_ACCESS_KEY',
        'AWS_STORAGE_BUCKET_NAME',
    ):
        monkeypatch.setenv(key, '')

    resolved = apply_storage_settings(media_url='/media/')

    assert 'FileSystemStorage' in resolved['default_file_storage']
    assert resolved['media_url'] == '/media/'
