"""
Why a post's media could not be loaded, and what the client should load now.

Where the bucket is private (S3_DEFAULT_ACL empty, as staging runs) every
media URL the API hands out is presigned, and stops working
S3_QUERYSTRING_EXPIRE seconds after the response -- an hour by default. The
web app kept those URLs for as long as a page stayed open and reused them
from its feed caches, and a card whose video failed once never asked again:
the post read "Video unavailable" until the page was rebuilt, and nothing on
the server ever heard about it.

The web app now reports a failed load to POST /api/v1/posts/media/ and plays
what comes back. This module is the server's half:

  diagnose()        why that URL failed -- one of REASONS -- from the URL
                    itself (its signature, whether it is still the post's
                    media) and, when that does not explain it, from storage
                    (does the object exist, will OBS let us read it, do our
                    clocks agree)
  check_failure()   diagnose, log `media.unavailable`, and return the post's
                    media signed now, less any rendition storage says is not
                    there; a post whose files are gone is queued for
                    re-processing from its original (repair)

Logged: the post, the rendition (model field), the storage key and the
storage status -- never a signature, never credentials. Nothing here returns
an original under source/: reel_media_payload never does, and a URL into
source/ is only ever diagnosed.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, unquote, urlsplit

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from api.services.media_pipeline import SOURCE_PREFIX, own_storage_key, storage_client

logger = logging.getLogger(__name__)

# What a diagnosis can say, and what it means. Also the vocabulary of the
# `media.unavailable` log line and of the `media_check.reason` the API
# returns; docs/media-pipeline.md lists the same.
REASONS = {
    'expired_signature': 'the signed URL had run out (issued longer ago than S3_QUERYSTRING_EXPIRE)',
    'superseded': 'the URL is for media the post no longer has (an edit or a re-process replaced it)',
    'object_missing': 'the object is not in the bucket',
    'access_denied': "storage refused the API's own credentials for the object",
    'storage_error': 'storage could not be asked (timeout, 5xx, connection refused)',
    'clock_skew': "the object is there and the URL in date by this server's clock, "
    "but storage's clock disagrees",
    'unsigned': 'an unsigned URL into a bucket whose objects are private',
    'original_requested': 'a URL into source/ -- originals are never served',
    'external': "not an object in this app's storage (an old Cloudinary URL, say)",
    'not_ready': 'the post is still processing, or failed',
    'available': 'nothing wrong on this side: the object is there and a fresh URL is valid '
    '(a network, codec or browser problem)',
}

# Logged as errors: something is wrong with the media or the deployment, and
# a fresh URL alone may not fix it. The rest are expected in normal use (a
# page left open past the signature lifetime) and logged at info.
_SERIOUS = {'object_missing', 'access_denied', 'storage_error', 'original_requested'}
_SUSPICIOUS = {'clock_skew', 'unsigned', 'external', 'available'}

VIDEO_RENDITIONS = ('media', 'media_480', 'media_360')
IMAGE_RENDITIONS = (
    'image',
    'image_medium',
    'image_small',
    'image_webp',
    'image_medium_webp',
    'image_small_webp',
)

# Where each model field appears in reel_media_payload.
_PAYLOAD_SLOT = {
    'media': ('media', None),
    'media_480': ('media_variants', '480'),
    'media_360': ('media_variants', '360'),
    'image': ('image', None),
    'image_medium': ('image_variants', '720'),
    'image_small': ('image_variants', '360'),
    'image_webp': ('image_webp_variants', 'full'),
    'image_medium_webp': ('image_webp_variants', '720'),
    'image_small_webp': ('image_webp_variants', '360'),
    'thumbnail': ('thumbnail', None),
}

PROBE_TTL = 60  # seconds one storage answer is reused across reports
REPAIR_TTL = 30 * 60  # at most one repair re-process per post per half hour
SKEW_TOLERANCE = 120  # seconds our clock and storage's may differ unremarked

_TOKEN = re.compile(r'[^A-Za-z0-9_.:-]')
_KEY = re.compile(r'[^A-Za-z0-9_./:@+=-]')


@dataclass
class Probe:
    """What storage said about one key."""

    state: str  # 'ok' | 'missing' | 'denied' | 'error'
    status: int | None = None
    skew: float | None = None  # storage's clock minus ours, in seconds


@dataclass
class Diagnosis:
    reason: str
    field: str | None = None
    key: str | None = None
    status: int | None = None
    skew: float | None = None


# -- URLs --------------------------------------------------------------------


def _query(url):
    try:
        return {k.lower(): v for k, v in parse_qsl(urlsplit(url).query, keep_blank_values=True)}
    except ValueError:
        return {}


def signature_expiry(url):
    """When a presigned URL stops working, or None when it is not signed.

    SigV4 (what django-storages produces) carries its issue time and lifetime
    as X-Amz-Date and X-Amz-Expires; the older V2 form, and OBS's own, carry
    an absolute Expires in epoch seconds.
    """
    query = _query(url or '')
    if 'x-amz-date' in query and 'x-amz-expires' in query:
        try:
            issued = datetime.strptime(query['x-amz-date'], '%Y%m%dT%H%M%SZ')
            return issued.replace(tzinfo=UTC) + timedelta(seconds=int(query['x-amz-expires']))
        except ValueError:
            return None
    if 'expires' in query and ('signature' in query or 'x-amz-signature' in query):
        try:
            return datetime.fromtimestamp(int(query['expires']), tz=UTC)
        except (ValueError, OverflowError, OSError):
            return None
    return None


def is_signed(url):
    query = _query(url or '')
    return 'x-amz-signature' in query or 'signature' in query


def stored_key(value):
    """The storage key a media field refers to, or None when the field is not
    an object in this app's storage."""
    value = str(value or '').strip()
    if not value:
        return None
    if value.startswith(('http://', 'https://')):
        return own_storage_key(value)
    media_url = getattr(settings, 'MEDIA_URL', '/media/') or '/media/'
    if media_url.startswith('/') and value.startswith(media_url):
        value = value[len(media_url) :]
    return value.lstrip('/') or None


def url_key(url):
    """The storage key a URL a client loaded points at, whatever form storage
    signed it in: path-style {endpoint}/{bucket}/{key}, virtual-hosted
    {bucket}.{host}/{key}, or a local /media/{key}."""
    base = (url or '').split('?', 1)[0].split('#', 1)[0]
    if not base:
        return None
    key = own_storage_key(base)
    if key:
        return key
    path = unquote(urlsplit(base).path)
    bucket = getattr(settings, 'S3_BUCKET_NAME', '') or ''
    if bucket and path.startswith(f'/{bucket}/'):
        return path[len(bucket) + 2 :] or None
    media_url = getattr(settings, 'MEDIA_URL', '/media/') or '/media/'
    if media_url.startswith('/') and path.startswith(media_url):
        return path[len(media_url) :] or None
    return path.lstrip('/') or None


def _storage_hosts():
    endpoint = (getattr(settings, 'S3_ENDPOINT_URL', '') or '').rstrip('/')
    host = urlsplit(endpoint).netloc.lower() if endpoint else ''
    bucket = (getattr(settings, 'S3_BUCKET_NAME', '') or '').lower()
    hosts = {h for h in (host, f'{bucket}.{host}' if bucket and host else '') if h}
    custom = (getattr(settings, 'S3_CUSTOM_DOMAIN', '') or '').lower()
    if custom:
        hosts.add(custom)
    return hosts


def _is_storage_url(url):
    netloc = urlsplit(url or '').netloc.lower()
    return bool(netloc) and netloc in _storage_hosts()


def _is_own_url(url):
    """A URL into this app's media: the bucket's host, or /media/ on the API
    (local storage)."""
    if _is_storage_url(url):
        return True
    media_url = getattr(settings, 'MEDIA_URL', '/media/') or '/media/'
    return media_url.startswith('/') and unquote(urlsplit(url or '').path).startswith(media_url)


def current_keys(reel):
    """{model field: storage key} for the media the post has now."""
    fields = (*VIDEO_RENDITIONS, *IMAGE_RENDITIONS, 'thumbnail')
    keys = {}
    for field in fields:
        key = stored_key(getattr(reel, field, ''))
        if key:
            keys[field] = key
    return keys


# -- storage -----------------------------------------------------------------


def _skew_from(response):
    try:
        date = (response.get('ResponseMetadata') or {}).get('HTTPHeaders', {}).get('date')
        if not date:
            return None
        return (parsedate_to_datetime(date) - timezone.now()).total_seconds()
    except (TypeError, ValueError, AttributeError):
        return None


def probe_storage(key):
    """Ask storage about `key` now: HEAD with the app's own credentials."""
    client = storage_client()
    if client is None:
        from django.core.files.storage import default_storage

        try:
            return Probe('ok', 200) if default_storage.exists(key) else Probe('missing', 404)
        except Exception:  # pragma: no cover - a filesystem that cannot be read
            return Probe('error')

    from botocore.exceptions import BotoCoreError, ClientError

    try:
        response = client.head_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
        return Probe('ok', 200, _skew_from(response))
    except ClientError as exc:
        response = getattr(exc, 'response', None) or {}
        status = (response.get('ResponseMetadata') or {}).get('HTTPStatusCode')
        code = str((response.get('Error') or {}).get('Code') or '')
        skew = _skew_from(response)
        if status == 404 or code in ('404', 'NoSuchKey', 'NotFound'):
            return Probe('missing', 404, skew)
        if status == 403 or code in ('403', 'AccessDenied', 'Forbidden'):
            return Probe('denied', 403, skew)
        return Probe('error', status, skew)
    except (BotoCoreError, OSError):
        return Probe('error')


def probe(key):
    """probe_storage, reused for PROBE_TTL: a post many people are watching
    fails for all of them at once, and storage need only be asked once."""
    cache_key = 'media:probe:' + hashlib.sha256(key.encode('utf-8')).hexdigest()
    hit = cache.get(cache_key)
    if hit:
        return Probe(*hit)
    result = probe_storage(key)
    cache.set(cache_key, (result.state, result.status, result.skew), PROBE_TTL)
    return result


# -- diagnosis ---------------------------------------------------------------


def diagnose(reel, url, now=None):
    """Why `url`, which a client could not load, failed for this post."""
    from api.models import MediaStatus

    now = now or timezone.now()
    if reel.processing_status != MediaStatus.READY:
        return Diagnosis('not_ready')

    keys = current_keys(reel)
    if not url:
        # Nothing to go on but the post: check its primary file.
        field = next((f for f in ('media', 'image') if f in keys), None)
        if field is None:
            return Diagnosis('object_missing')
        return _from_storage(field, keys[field])

    key = url_key(url)
    if key and key.startswith(SOURCE_PREFIX):
        return Diagnosis('original_requested', key=key)

    field = next((f for f, k in keys.items() if k == key), None)
    if field is None:
        # Not a URL of the media the post has now: a processed path of this
        # post under an earlier version, or a file the post used to have. The
        # client held on to media an edit or a re-process has since replaced.
        # A URL outside this app's media altogether is someone else's.
        if urlsplit(url).netloc and not _is_own_url(url):
            return Diagnosis('external', key=key)
        return Diagnosis('superseded', key=key)

    expiry = signature_expiry(url)
    if expiry is not None and expiry <= now:
        return Diagnosis('expired_signature', field, key)
    if (
        getattr(settings, 'AWS_QUERYSTRING_AUTH', False)
        and _is_storage_url(url)
        and not is_signed(url)
    ):
        return Diagnosis('unsigned', field, key)
    return _from_storage(field, key)


def _from_storage(field, key):
    """The URL does not explain the failure; ask storage about the object."""
    result = probe(key)
    reason = {'missing': 'object_missing', 'denied': 'access_denied', 'error': 'storage_error'}.get(
        result.state
    )
    if reason is None:
        skewed = result.skew is not None and abs(result.skew) > SKEW_TOLERANCE
        reason = 'clock_skew' if skewed else 'available'
    return Diagnosis(reason, field, key, result.status, result.skew)


def missing_renditions(reel):
    """Model fields whose object storage says is not there."""
    return {field for field, key in current_keys(reel).items() if probe(key).state == 'missing'}


def repair(reel, missing):
    """Re-process a READY post whose files are gone, from its original.

    The post stays READY on whatever it still has; the task writes a new
    version and the post moves to it (process_reel_media's backfill path).
    Once per REPAIR_TTL per post, and only when the original is still there.
    """
    from api.tasks.media import process_reel_media

    if not missing or not (reel.original_media or reel.original_image):
        return False
    if getattr(reel, 'source_deleted_at', None):
        return False
    if not cache.add(f'media:repair:{reel.pk}', 1, REPAIR_TTL):
        return True  # already queued recently
    try:
        process_reel_media.delay(reel.pk, force=True)
    except Exception:  # pragma: no cover - broker down: the next report retries
        cache.delete(f'media:repair:{reel.pk}')
        logger.exception('media.repair could not queue reel=%s', reel.pk)
        return False
    logger.warning('media.repair_queued reel=%s missing=%s', reel.pk, ','.join(sorted(missing)))
    return True


def without_renditions(payload, missing):
    """reel_media_payload with the renditions in `missing` taken out; a
    primary that is gone is replaced by the best rendition that is not."""
    for field in missing:
        slot, sub = _PAYLOAD_SLOT.get(field, (None, None))
        if slot is None:
            continue
        if sub is None:
            payload[slot] = None
        elif isinstance(payload.get(slot), dict):
            payload[slot].pop(sub, None)
            if not payload[slot]:
                payload[slot] = None
    for primary, variants, order in (
        ('media', 'media_variants', ('480', '360')),
        ('image', 'image_variants', ('720', '360')),
    ):
        if payload.get(primary) is None and payload.get(variants):
            payload[primary] = next(
                (payload[variants][k] for k in order if payload[variants].get(k)), None
            )
    return payload


def media_payload(reel, request):
    """reel_media_payload -- and nothing to load while the post is not READY,
    whatever its fields hold: processing posts point at their original, and
    an original is never served."""
    from api.models import MediaStatus
    from api.serializers.core import reel_media_payload

    payload = reel_media_payload(reel, request)
    if reel.processing_status != MediaStatus.READY:
        payload = without_renditions(payload, _PAYLOAD_SLOT)
    return payload


def _token(value, limit=32):
    return _TOKEN.sub('', str(value or ''))[:limit] or '-'


def _key_token(value):
    # A key can come from the client's URL (superseded, external): nothing
    # but key characters reaches the log, so it cannot forge a line.
    return _KEY.sub('', str(value or ''))[:300] or '-'


def check_failure(reel, failure, request):
    """Diagnose one reported failure, log it, and return
    (the post's media to load now, {'reason', 'repairing'})."""
    url = str(failure.get('url') or '')[:2048]
    diagnosis = diagnose(reel, url)
    missing = set()
    repairing = False
    if diagnosis.reason == 'object_missing':
        missing = missing_renditions(reel)
        repairing = repair(reel, missing)

    level = (
        logging.ERROR
        if diagnosis.reason in _SERIOUS
        else logging.WARNING
        if diagnosis.reason in _SUSPICIOUS
        else logging.INFO
    )
    viewer = request.user.pk if getattr(request.user, 'is_authenticated', False) else 'anon'
    logger.log(
        level,
        'media.unavailable reel=%s field=%s reason=%s status=%s skew=%s surface=%s error=%s '
        'key=%s missing=%s repairing=%s viewer=%s',
        reel.pk,
        diagnosis.field or '-',
        diagnosis.reason,
        diagnosis.status if diagnosis.status is not None else '-',
        f'{diagnosis.skew:.0f}' if diagnosis.skew is not None else '-',
        _token(failure.get('surface')),
        _token(failure.get('error')),
        _key_token(diagnosis.key),
        ','.join(sorted(missing)) or '-',
        repairing,
        viewer,
    )

    payload = without_renditions(media_payload(reel, request), missing)
    return payload, {'reason': diagnosis.reason, 'repairing': repairing}
