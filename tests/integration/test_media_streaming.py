"""
Byte-serving uploaded media over HTTP.

Covers what a video element actually does: ask for metadata, seek by asking
for a middle range, read the tail of an MP4 to find its moov atom, and give up
on anything that answers 200-with-everything.
"""

from __future__ import annotations

import pytest
from django.test import Client, override_settings

pytestmark = pytest.mark.integration

SMALL = b'0123456789' * 10          # 100 bytes
LARGE = bytes(range(256)) * 40_000  # ~10 MB


@pytest.fixture
def media_root(tmp_path, settings):
    root = tmp_path / 'media'
    (root / 'reels').mkdir(parents=True)
    settings.MEDIA_ROOT = str(root)
    # default_storage caches its location, so point it at the temp root too.
    from django.core.files.storage import default_storage

    default_storage._location = None
    default_storage.__dict__.pop('base_location', None)
    default_storage.__dict__.pop('location', None)
    return root


@pytest.fixture
def small_video(media_root):
    p = media_root / 'reels' / 'small.mp4'
    p.write_bytes(SMALL)
    return '/media/reels/small.mp4'


@pytest.fixture
def large_video(media_root):
    p = media_root / 'reels' / 'large.mp4'
    p.write_bytes(LARGE)
    return '/media/reels/large.mp4'


@pytest.fixture
def client():
    return Client()


def body(response) -> bytes:
    return b''.join(response.streaming_content) if response.streaming else response.content


# ─── the capability a player looks for ────────────────────────────────────────

def test_a_plain_request_advertises_range_support(client, small_video):
    r = client.get(small_video)

    assert r.status_code == 200
    assert r['Accept-Ranges'] == 'bytes'
    assert r['Content-Length'] == str(len(SMALL))
    assert r['Content-Type'] == 'video/mp4'


def test_a_range_request_returns_206_with_only_those_bytes(client, small_video):
    r = client.get(small_video, HTTP_RANGE='bytes=10-19')

    assert r.status_code == 206
    assert r['Content-Range'] == f'bytes 10-19/{len(SMALL)}'
    assert r['Content-Length'] == '10'
    assert body(r) == SMALL[10:20]


def test_seeking_into_the_middle_returns_the_right_bytes(client, large_video):
    start, end = 5_000_000, 5_000_099
    r = client.get(large_video, HTTP_RANGE=f'bytes={start}-{end}')

    assert r.status_code == 206
    assert body(r) == LARGE[start:end + 1]


def test_an_open_ended_range_streams_to_the_end(client, small_video):
    r = client.get(small_video, HTTP_RANGE='bytes=90-')

    assert r.status_code == 206
    assert r['Content-Range'] == f'bytes 90-99/{len(SMALL)}'
    assert body(r) == SMALL[90:]


def test_a_suffix_range_returns_the_tail(client, small_video):
    r = client.get(small_video, HTTP_RANGE='bytes=-10')

    assert r.status_code == 206
    assert body(r) == SMALL[-10:]


def test_an_over_long_upper_bound_is_clamped_not_refused(client, small_video):
    """Players send bytes=0-99999999; a 416 here stalls playback."""
    r = client.get(small_video, HTTP_RANGE='bytes=0-99999999')

    assert r.status_code == 206
    assert r['Content-Range'] == f'bytes 0-99/{len(SMALL)}'


def test_an_unsatisfiable_range_gets_416_with_the_size(client, small_video):
    r = client.get(small_video, HTTP_RANGE='bytes=500-600')

    assert r.status_code == 416
    assert r['Content-Range'] == f'bytes */{len(SMALL)}'


# ─── not loading whole files ──────────────────────────────────────────────────

def test_a_large_video_is_not_delivered_whole_for_a_small_range(client, large_video):
    """The first thing a player asks for is a small opening slice."""
    r = client.get(large_video, HTTP_RANGE='bytes=0-1023')

    assert r.status_code == 206
    assert r['Content-Length'] == '1024'
    assert len(body(r)) == 1024


def test_a_large_range_arrives_in_chunks_not_one_blob(client, large_video):
    """Proves the response streams: more than one chunk reaches the client."""
    r = client.get(large_video, HTTP_RANGE='bytes=0-999999')

    chunks = list(r.streaming_content)
    assert len(chunks) > 1, 'response was materialised as a single buffer'
    assert sum(len(c) for c in chunks) == 1_000_000


def test_head_reports_size_without_a_body(client, large_video):
    r = client.head(large_video)

    assert r.status_code == 200
    assert r['Content-Length'] == str(len(LARGE))
    assert r['Accept-Ranges'] == 'bytes'
    assert body(r) == b''


# ─── caching / conditional requests ───────────────────────────────────────────

def test_a_matching_etag_gets_304(client, small_video):
    first = client.get(small_video)
    etag = first['ETag']

    second = client.get(small_video, HTTP_IF_NONE_MATCH=etag)

    assert second.status_code == 304


# ─── refusing what it should ──────────────────────────────────────────────────

@pytest.mark.parametrize(
    'path',
    [
        '/media/../../etc/passwd',
        '/media/reels/../../../etc/passwd',
        '/media/reels/../../settings.py',
    ],
)
def test_path_traversal_is_refused(client, media_root, path):
    r = client.get(path)
    assert r.status_code in (404, 400), f'{path} returned {r.status_code}'


def test_a_missing_file_is_404(client, media_root):
    assert client.get('/media/reels/nope.mp4').status_code == 404


@pytest.mark.parametrize('method', ['post', 'put', 'delete', 'patch'])
def test_write_methods_are_refused(client, small_video, method):
    r = getattr(client, method)(small_video)
    assert r.status_code == 405


# ─── offloading instead of proxying ───────────────────────────────────────────

@override_settings(MEDIA_INTERNAL_LOCATION='/protected-media/')
def test_nginx_offload_hands_the_file_over_without_streaming_it(client, small_video):
    """With nginx in front, no video bytes should pass through the worker."""
    r = client.get(small_video, HTTP_RANGE='bytes=0-9')

    assert r.status_code == 200
    assert r['X-Accel-Redirect'] == '/protected-media/reels/small.mp4'
    assert r.content == b''
