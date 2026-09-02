"""
Byte-serving for uploaded media.

The cheapest way to stream a video is not to stream it from Django at all, so
this picks the best available offload before falling back to doing the work
itself:

1. **Object storage** -- redirect to a short-lived signed URL and let S3/MinIO
   serve the bytes. It already speaks ``Range`` correctly, and no video data
   passes through a worker.
2. **nginx in front** -- hand back ``X-Accel-Redirect`` and let nginx serve the
   file from disk. Same benefit, for deployments without object storage.
3. **Neither** -- stream from local disk here, in chunks, with correct
   ``206``/``Content-Range`` handling.

Only the third path moves bytes through the application, and even then it holds
one 64 KB chunk at a time rather than the whole requested span.

Replaces ``api/views/video.py``, which was never routed and could not safely be:
it joined unvalidated user input onto ``MEDIA_ROOT`` (so ``../../`` escaped it),
read whole ranges into memory, answered 416 to the open-ended upper bounds real
players send, and passed a ``bytes`` object to ``StreamingHttpResponse`` -- which
iterates it into one integer per byte.
"""

from __future__ import annotations

import mimetypes
import os
import posixpath
import unicodedata
from urllib.parse import quote

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import (
    FileResponse,
    HttpResponse,
    HttpResponseNotModified,
    HttpResponsePermanentRedirect,
    HttpResponseRedirect,
    StreamingHttpResponse,
)
from django.utils.http import http_date
from django.views.decorators.http import require_http_methods

from common.http.ranges import RangeNotSatisfiable, file_chunks, parse_range_header

#: Set to nginx's internal location (e.g. ``/protected-media/``) to hand file
#: serving off via X-Accel-Redirect. Left unset, media is streamed from here.
INTERNAL_REDIRECT_SETTING = 'MEDIA_INTERNAL_LOCATION'

#: How long a redirect to object storage stays usable. Short enough that a
#: leaked URL expires quickly, long enough to watch a clip through.
SIGNED_URL_TTL_SECONDS = 3600


def _safe_relative_name(path: str) -> str | None:
    """Normalise `path` to a storage-relative name, or None if it escapes.

    Everything is rejected that could resolve outside the media root: parent
    traversal, absolute paths, and Windows drive letters or backslashes (the
    server may be POSIX, but the check should not depend on that).
    """
    if not path:
        return None

    # A NUL byte truncates the path in some C-level calls.
    if '\x00' in path:
        return None

    # Normalise unicode first: some forms decompose into characters that
    # normalise back into '.' or '/' later in the stack.
    path = unicodedata.normalize('NFKC', path)

    if path.startswith('/') or path.startswith('\\') or '\\' in path:
        return None
    if ':' in path.split('/')[0]:
        return None

    normalised = posixpath.normpath(path)
    if normalised.startswith('..') or normalised.startswith('/') or normalised == '.':
        return None
    if any(part == '..' for part in normalised.split('/')):
        return None

    return normalised


def _content_type_for(name: str) -> str:
    guessed, _encoding = mimetypes.guess_type(name)
    return guessed or 'application/octet-stream'


def _is_remote_storage(storage) -> bool:
    """True when the storage backend serves its own URLs (S3/MinIO)."""
    # FileSystemStorage exposes a usable `path()`; remote backends raise
    # NotImplementedError from it, which is the documented way to tell them
    # apart without importing django-storages.
    try:
        storage.path('probe')
    except NotImplementedError:
        return True
    except Exception:
        return False
    return False


def _signed_url(storage, name: str) -> str | None:
    try:
        return storage.url(name)
    except Exception:
        return None


def _apply_common_headers(response, *, name: str, size: int | None, mtime: float | None):
    response['Accept-Ranges'] = 'bytes'
    # Media is immutable once uploaded (filenames carry a unique suffix), so a
    # long cache is safe and spares mobile clients re-fetching on every scroll.
    response['Cache-Control'] = 'public, max-age=31536000, immutable'
    if mtime is not None:
        response['Last-Modified'] = http_date(mtime)
    if size is not None and mtime is not None:
        # Weak validator: enough for conditional requests without hashing the file.
        response['ETag'] = f'W/"{int(mtime)}-{size}"'
    response['Content-Disposition'] = f"inline; filename*=UTF-8''{quote(posixpath.basename(name))}"
    return response


@require_http_methods(['GET', 'HEAD'])
def serve_media(request, path):
    """Serve an uploaded file, with range support and the cheapest offload."""
    name = _safe_relative_name(path)
    if name is None:
        return HttpResponse(status=404)

    storage = default_storage

    if not storage.exists(name):
        return HttpResponse(status=404)

    # ── 1. Object storage: let S3 do the byte-serving. ──────────────────────
    if _is_remote_storage(storage):
        url = _signed_url(storage, name)
        if url:
            # Temporary, not permanent: the signature expires, so this must
            # never be cached as a durable mapping.
            response = HttpResponseRedirect(url)
            response['Cache-Control'] = 'private, max-age=60'
            return response
        return HttpResponse(status=502)

    # ── 2. nginx in front: hand it the file. ───────────────────────────────
    internal_location = getattr(settings, INTERNAL_REDIRECT_SETTING, '')
    if internal_location:
        response = HttpResponse(status=200)
        response['X-Accel-Redirect'] = posixpath.join(internal_location.rstrip('/') + '/', name)
        # nginx fills in length and range headers; Django must not.
        del response['Content-Type']
        response['Accept-Ranges'] = 'bytes'
        return response

    # ── 3. Serve it here, in chunks. ───────────────────────────────────────
    try:
        full_path = storage.path(name)
        size = os.path.getsize(full_path)
        mtime = os.path.getmtime(full_path)
    except (NotImplementedError, OSError):
        return HttpResponse(status=404)

    content_type = _content_type_for(name)

    if request.headers.get('If-None-Match') == f'W/"{int(mtime)}-{size}"':
        return _apply_common_headers(
            HttpResponseNotModified(), name=name, size=size, mtime=mtime
        )

    try:
        spec = parse_range_header(request.headers.get('Range'), size)
    except RangeNotSatisfiable:
        response = HttpResponse(status=416)
        response['Content-Range'] = f'bytes */{size}'
        response['Accept-Ranges'] = 'bytes'
        return response

    if request.method == 'HEAD':
        response = HttpResponse(content_type=content_type)
        response['Content-Length'] = str(size)
        return _apply_common_headers(response, name=name, size=size, mtime=mtime)

    if spec is None:
        # No range asked for: still advertise support, so the player knows it
        # may seek without re-requesting from zero.
        response = FileResponse(open(full_path, 'rb'), content_type=content_type)
        response['Content-Length'] = str(size)
        return _apply_common_headers(response, name=name, size=size, mtime=mtime)

    response = StreamingHttpResponse(
        file_chunks(open(full_path, 'rb'), spec.start, spec.length),
        status=206,
        content_type=content_type,
    )
    response['Content-Range'] = spec.content_range
    response['Content-Length'] = str(spec.length)
    return _apply_common_headers(response, name=name, size=size, mtime=mtime)
