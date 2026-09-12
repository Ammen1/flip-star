"""
One way in for post media, whichever client and whichever endpoint.

Web and mobile both upload through Django (multipart), to /posts/create/,
/reels/ or /campaigns/posts/create/. This module is what those views share:

  validate_upload     size, and the file's real type from its first bytes --
                      never the filename or the client's Content-Type
  store_source        writes the original to object storage (Ethio Telecom
                      OBS) under source/, privately: it is input for the
                      worker, never something a client is served
  read_client_upload_id / existing_post
                      the Idempotency-Key a client sends so a retry returns
                      the post it already made instead of a second one
  queue_processing    hands the post to api.tasks.media.process_reel_media
                      once the transaction commits

What the request no longer does is run FFmpeg: no duration probe, no frame
grab, no metadata remux. It stores the bytes, records the post as PROCESSING
and answers; everything else happens on the workers.
"""

import logging
import re
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)

VIDEO = 'video'
IMAGE = 'image'
SOURCE_PREFIX = 'source/'

# ISO-BMFF brands that are still images, not video: HEIC/HEIF photos from
# phones. Pillow cannot decode them, so they are refused at upload with a
# clear message rather than failing later on a worker.
_HEIF_BRANDS = {b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1', b'avif'}


class MediaRejected(Exception):
    """An upload the API refuses, with a message fit to show the person."""

    def __init__(self, code, message, http_status=status.HTTP_400_BAD_REQUEST):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status

    def response(self):
        return Response({'error': self.message, 'code': self.code}, status=self.http_status)


class StorageUnavailable(Exception):
    """The original could not be written to object storage."""


@dataclass(frozen=True)
class Intake:
    kind: str  # VIDEO or IMAGE
    ext: str
    content_type: str
    size: int


def sniff(upload_file):
    """(kind, extension, content type) from the file's first bytes, or None."""
    upload_file.seek(0)
    head = upload_file.read(64)
    upload_file.seek(0)

    if head[:3] == b'\xff\xd8\xff':
        return IMAGE, 'jpg', 'image/jpeg'
    if head[:8] == b'\x89PNG\r\n\x1a\n':
        return IMAGE, 'png', 'image/png'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return IMAGE, 'webp', 'image/webp'
    if head[4:8] == b'ftyp':
        brand = head[8:12]
        if brand in _HEIF_BRANDS:
            return 'heif', 'heic', 'image/heic'
        if brand == b'qt  ':
            return VIDEO, 'mov', 'video/quicktime'
        return VIDEO, 'mp4', 'video/mp4'
    if head[:4] == b'\x1a\x45\xdf\xa3':
        if b'webm' in head:
            return VIDEO, 'webm', 'video/webm'
        return VIDEO, 'mkv', 'video/x-matroska'
    if head[:4] == b'RIFF' and head[8:12] == b'AVI ':
        return VIDEO, 'avi', 'video/x-msvideo'
    return None


def validate_upload(upload_file):
    """The accepted shape of an upload, or MediaRejected saying what is wrong."""
    if not upload_file:
        raise MediaRejected('file_required', 'Choose a photo or video to post.')
    size = getattr(upload_file, 'size', 0) or 0
    if size == 0:
        raise MediaRejected(
            'empty_file',
            'The file is empty. If you recorded a video, please record it again.',
        )
    limit = settings.MEDIA_MAX_UPLOAD_BYTES
    if size > limit:
        raise MediaRejected(
            'file_too_large',
            f'Files can be at most {limit // (1024 * 1024)} MB.',
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    sniffed = sniff(upload_file)
    if sniffed and sniffed[0] == 'heif':
        raise MediaRejected(
            'unsupported_image_format',
            'HEIC photos are not supported yet. Choose a JPEG, PNG or WebP photo.',
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )
    if not sniffed:
        raise MediaRejected(
            'unsupported_file',
            'This file type is not supported. Post a JPEG, PNG or WebP photo, '
            'or an MP4, MOV or WebM video.',
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )
    kind, ext, content_type = sniffed

    if kind == IMAGE:
        # Only the header is read: Image.open is lazy, so this costs no decode.
        from PIL import Image

        try:
            with Image.open(upload_file) as img:
                width, height = img.size
        except Image.DecompressionBombError as exc:
            raise MediaRejected('image_too_large', 'This photo is too large to post.') from exc
        except Exception as exc:
            raise MediaRejected('unreadable_image', 'This photo could not be read.') from exc
        finally:
            upload_file.seek(0)
        if width * height > settings.MEDIA_MAX_IMAGE_PIXELS:
            raise MediaRejected('image_too_large', 'This photo is too large to post.')

    return Intake(kind=kind, ext=ext, content_type=content_type, size=size)


_source_storage = None


def source_storage():
    """Where originals are kept: the same bucket, but private.

    Where the rest of the app writes public-read objects, originals are
    written with an explicit private ACL: they are never served. Where no ACL
    is configured (S3_DEFAULT_ACL empty: objects are private by default, or
    the bucket refuses ACL headers) none is sent. The worker reads them with
    its own credentials either way.
    """
    global _source_storage
    if _source_storage is None:
        from infrastructure.storage.config import S3_STORAGE

        if getattr(settings, 'DEFAULT_FILE_STORAGE', '') == S3_STORAGE:
            from storages.backends.s3boto3 import S3Boto3Storage

            _source_storage = S3Boto3Storage(
                default_acl='private' if getattr(settings, 'AWS_DEFAULT_ACL', None) else None,
                querystring_auth=True,
                object_parameters={'CacheControl': 'private, no-store'},
            )
        else:
            # Local filesystem (development, tests): no ACLs to set.
            _source_storage = default_storage
    return _source_storage


def source_key(user_id, kind, ext):
    """source/<videos|images>/<user id>/<random>.<ext> -- never client-chosen."""
    return f'{SOURCE_PREFIX}{kind}s/{user_id}/{uuid.uuid4().hex}.{ext}'


def store_source(user, upload_file, intake):
    """Write the original to private storage; return its key."""
    key = source_key(user.pk, intake.kind, intake.ext)
    upload_file.seek(0)
    try:
        return source_storage().save(key, upload_file)
    except Exception as exc:
        logger.exception('media.store_source failed user=%s kind=%s', user.pk, intake.kind)
        raise StorageUnavailable(key) from exc


def discard_source(key):
    """Remove an original that no post ended up using. Best effort."""
    if not key:
        return
    try:
        source_storage().delete(key)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning('media.discard_source could not delete %s: %s', key, exc)


_CLIENT_ID = re.compile(r'^[A-Za-z0-9_.:\-]{8,64}$')


def read_client_upload_id(request):
    """The client's id for this submission, from the Idempotency-Key header
    or a `client_upload_id` form field (for clients that cannot set headers
    on a multipart request). Empty when the client sent none."""
    raw = request.headers.get('Idempotency-Key') or request.data.get('client_upload_id') or ''
    raw = str(raw).strip()
    if not raw:
        return ''
    if not _CLIENT_ID.match(raw):
        raise MediaRejected(
            'invalid_idempotency_key',
            'Idempotency-Key must be 8-64 letters, digits, dots, dashes, underscores or colons.',
        )
    return raw


def existing_post(user, client_upload_id):
    """The post this user already made with this submission id, if any."""
    if not client_upload_id:
        return None
    from api.models import Reel

    return Reel.objects.filter(user=user, client_upload_id=client_upload_id).first()


def queue_processing(reel_id):
    """Queue processing once the surrounding transaction commits.

    robust: a broker outage at this moment must not turn a stored, paid-for
    post into a 500. The post stays PROCESSING and redrive_stuck_media picks
    it up within ten minutes.
    """
    from api.tasks.media import process_reel_media

    def _send():
        process_reel_media.delay(reel_id)

    transaction.on_commit(_send, robust=True)


def own_storage_key(url):
    """The key of a full URL into this app's own bucket -- the form the worker
    records processed media in, {S3_ENDPOINT_URL}/{bucket}/{key} -- or None."""
    endpoint = (getattr(settings, 'S3_ENDPOINT_URL', '') or '').rstrip('/')
    bucket = getattr(settings, 'S3_BUCKET_NAME', '') or ''
    if not (url and endpoint and bucket):
        return None
    prefix = f'{endpoint}/{bucket}/'
    if not url.startswith(prefix):
        return None
    return url[len(prefix) :].split('?', 1)[0] or None


def servable_url(url):
    """A stored full URL as a client should load it.

    Where the bucket's objects are not public (AWS_QUERYSTRING_AUTH -- which
    is on whenever S3_DEFAULT_ACL is not public-read) an unsigned URL answers
    403, and the worker records processed media as unsigned URLs. Those are
    signed here, the way storage signs every other media URL; anything else
    passes through unchanged. A source/ original is never returned.
    """
    key = own_storage_key(url)
    if key is None:
        return url
    if key.startswith(SOURCE_PREFIX):
        return None
    if not getattr(settings, 'AWS_QUERYSTRING_AUTH', False):
        return url
    try:
        return default_storage.url(key)
    except Exception as exc:  # pragma: no cover - fall back to what was stored
        logger.warning('media.servable_url could not sign %s: %s', key, exc)
        return url


def served_url(field, request=None):
    """The URL a client may load for a stored media field, or None.

    For views that build post dicts by hand rather than through
    ReelSerializer. Pipeline output is recorded as its full URL and is
    returned as-is: asking storage for .url() of a full URL mangles it into a
    key. Originals under source/ are private input for the worker and are
    never returned. Anything else is resolved by storage and made absolute.
    """
    if not field:
        return None
    name = str(getattr(field, 'name', field) or '')
    if not name:
        return None
    if name.startswith(('http://', 'https://')):
        return servable_url(name)
    if name.startswith(SOURCE_PREFIX):
        return None
    try:
        url = field.url if hasattr(field, 'url') else default_storage.url(name)
    except Exception:
        return None
    if not url:
        return None
    if url.startswith(('http://', 'https://')) or request is None:
        return url
    return request.build_absolute_uri(url)


def processed_media_exists(reel):
    """Whether the post's processed primary file is actually in storage."""
    from api.tasks.media import PROCESSED_PREFIX

    value = str(reel.media or '') if reel.original_media else str(reel.image or '')
    if not value:
        return False
    if value.startswith(('http://', 'https://')):
        marker = f'/{PROCESSED_PREFIX}'
        if marker not in value:
            return False
        key = value[value.index(marker) + 1 :]
    else:
        key = value
    if not key.startswith(PROCESSED_PREFIX):
        return False
    try:
        if settings.S3_BUCKET_NAME:
            import boto3
            from botocore.exceptions import ClientError

            kwargs = {
                'aws_access_key_id': settings.S3_ACCESS_KEY_ID,
                'aws_secret_access_key': settings.S3_SECRET_ACCESS_KEY,
                'region_name': settings.S3_REGION_NAME,
            }
            if settings.S3_ENDPOINT_URL:
                kwargs['endpoint_url'] = settings.S3_ENDPOINT_URL
            try:
                boto3.client('s3', **kwargs).head_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
                return True
            except ClientError:
                return False
        return default_storage.exists(key)
    except Exception as exc:  # pragma: no cover - treat as "not confirmed"
        logger.warning('media.processed_media_exists could not check %s: %s', key, exc)
        return False
