import logging
import mimetypes
import os
import shutil
import tempfile
import time
import uuid
from datetime import timedelta

import redis
import requests as http_requests
from celery import shared_task
from django.conf import settings
from django.db import DataError
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# Credentials come from Django settings, which resolve through
# environment -> Vault -> .env. This module previously read ACCESS_KEY_ID,
# SECRET_ACCESS_KEY and FIREBASE_SERVER_KEY straight from decouple, which
# bypassed Vault entirely.

_redis_client = None


def _get_redis():
    """Lazily connect to Redis.

    Built on first use rather than at import, so merely importing this module
    (which `celery inspect`, `manage.py` and the test collector all do) does not
    open a socket.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
        )
    return _redis_client


# ── Presence cleanup ────────────────────────────────────────────────────────


@shared_task
def cleanup_typing_indicators():
    """Clean up expired typing indicators from Redis."""
    try:
        keys = _get_redis().keys('typing:*')
        return f'Found {len(keys)} active typing indicators'
    except Exception as e:
        return f'Error: {str(e)}'


# ── Helpers ─────────────────────────────────────────────────────────────────


def _fetch_to_temp(url, suffix):
    """Download a remote URL to a NamedTemporaryFile; caller must delete."""
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        resp = http_requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        for chunk in resp.iter_content(8192):
            tmp.write(chunk)
    finally:
        tmp.close()
    return tmp.name


def _local_path(value):
    """Resolve a stored field value (URL or relative path) to an abs path."""
    if not value:
        return None
    if value.startswith('http://') or value.startswith('https://'):
        return None  # needs download — handled per-task
    if value.startswith('/'):
        return value
    return os.path.join(settings.MEDIA_ROOT, value)


class _Progress:
    """How far the worker is with a post, written to ``processing_progress``
    as the work actually completes -- bytes of the original fetched, seconds
    FFmpeg reports encoded, outputs stored -- never estimated from time.

    Written only upwards within a run, at most about once a second (or on a
    jump of MIN_STEP points), and only while this run still holds the post.
    Capped at 99: 100 is written together with READY. A post that is already
    being served (a backfill) reports nothing -- nobody is waiting on it.
    """

    MIN_INTERVAL = 1.0
    MIN_STEP = 5

    def __init__(self, reel_id=None, task_id=None, enabled=True):
        self.reel_id = reel_id
        self.task_id = task_id
        self.enabled = enabled and reel_id is not None
        self.written = 0
        self.written_at = 0.0

    def to(self, percent, force=False):
        if not self.enabled:
            return
        value = max(0, min(99, int(percent)))
        if value <= self.written:
            return
        now = time.monotonic()
        if not force and value - self.written < self.MIN_STEP:
            if now - self.written_at < self.MIN_INTERVAL:
                return
        self._write(value)
        self.written = value
        self.written_at = now

    def _write(self, value):
        from api.models import Reel

        Reel.objects.filter(pk=self.reel_id, processing_task_id=self.task_id).update(
            processing_progress=value
        )

    def span(self, start, end):
        """A callback for one stage: the fraction (0-1) of that stage done,
        mapped into start..end of the whole."""

        def report(fraction, force=False):
            share = max(0.0, min(1.0, float(fraction or 0)))
            self.to(start + (end - start) * share, force=force)

        return report


_NO_PROGRESS = _Progress(enabled=False)


def _fetch_source(value, workdir, suffix, on_progress=None, total=None):
    """A local copy of the original upload, wherever it lives.

    New uploads are keys under ``source/`` in private storage, so they are
    read through the storage API with the worker's credentials -- there is no
    public URL to download them from, by design. Older posts hold a public URL
    or a MEDIA_ROOT path, and are read the way they always were.

    ``on_progress`` gets the share of ``total`` bytes copied so far.
    """
    if not value:
        return None
    if value.startswith(('http://', 'https://')):
        path = os.path.join(workdir, f'source{suffix}')
        tmp = _fetch_to_temp(value, suffix)
        shutil.move(tmp, path)
        return path
    if value.startswith(SOURCE_PREFIX):
        from api.services.media_pipeline import source_storage

        path = os.path.join(workdir, f'source{suffix}')
        copied = 0
        with source_storage().open(value, 'rb') as src, open(path, 'wb') as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
                copied += len(chunk)
                if on_progress and total:
                    on_progress(copied / total)
        return path
    return _local_path(value)


def _upload_to_s3(local_path, s3_key):
    """Upload a file to S3/MinIO/OBS and return its public URL, or None.

    Credentials come from Django settings (resolved via environment -> Vault ->
    .env), so the worker uses exactly the same values as the web process.

    Content-Type is always sent: without it the object is stored as
    binary/octet-stream, which some players refuse to stream. Keys under
    processed/ also get the year-long immutable Cache-Control: they carry a
    version and are never rewritten. Other keys -- a profile photo, which is
    overwritten in place -- must stay revalidatable, so they do not.
    """
    immutable = s3_key.startswith(PROCESSED_PREFIX)
    bucket = settings.S3_BUCKET_NAME
    endpoint_url = settings.S3_ENDPOINT_URL
    region = settings.S3_REGION_NAME
    if not bucket:
        return None
    try:
        import boto3

        s3_kwargs = {
            'aws_access_key_id': settings.S3_ACCESS_KEY_ID,
            'aws_secret_access_key': settings.S3_SECRET_ACCESS_KEY,
            'region_name': region,
        }
        if endpoint_url:
            s3_kwargs['endpoint_url'] = endpoint_url

        extra = {'ContentType': mimetypes.guess_type(s3_key)[0] or 'application/octet-stream'}
        # The same ACL the web process writes with, and none when none is
        # configured. S3_DEFAULT_ACL= (empty) leaves AWS_DEFAULT_ACL undefined;
        # this used to fall back to public-read regardless, so on a bucket
        # that refuses public ACLs every processed file failed to upload and
        # every post ended FAILED after its retries.
        acl = getattr(settings, 'AWS_DEFAULT_ACL', None)
        if acl:
            extra['ACL'] = acl
        if immutable:
            extra['CacheControl'] = getattr(settings, 'AWS_S3_OBJECT_PARAMETERS', {}).get(
                'CacheControl', 'public, max-age=31536000, immutable'
            )

        s3 = boto3.client('s3', **s3_kwargs)
        s3.upload_file(local_path, bucket, s3_key, ExtraArgs=extra)

        if endpoint_url:
            return f'{endpoint_url}/{bucket}/{s3_key}'
        else:
            return f'https://{bucket}.s3.{region}.amazonaws.com/{s3_key}'
    except Exception as e:
        logger.warning('[TASKS] S3/OBS upload failed for %s: %s', s3_key, e)
        return None


def _publish(local_path, s3_key, discard=None):
    """Store a processed artefact under ``s3_key``; return what to record.

    With object storage configured that is the object's URL. ``discard`` gets
    the local path only once the upload has succeeded -- deleting a file that
    never reached storage would leave the post pointing at nothing -- and
    ``discard=None`` protects a path that must survive regardless. (The task
    itself works in a temporary directory that it removes wholesale.)

    Without object storage (a development box) the file is placed at
    MEDIA_ROOT/<key> and the relative key is recorded, which the serializer
    resolves through default_storage. Returns None when storage is configured
    but refused the upload: the caller treats that rendition as absent rather
    than recording a path on this worker's disk that no client can reach.
    """
    url = _upload_to_s3(local_path, s3_key)
    if url:
        if discard is not None:
            discard.append(local_path)
        return url
    if settings.S3_BUCKET_NAME:
        return None
    target = os.path.join(settings.MEDIA_ROOT, s3_key)
    if os.path.abspath(local_path) != os.path.abspath(target):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.move(local_path, target)
    return s3_key


def _delete_version(reel_id, version=None, keep=None):
    """Remove a post's processed outputs: one run's (``version``), every run
    but the one in use (``keep``), or all of them (neither: the post itself
    was deleted). Best effort; logged, never raised."""
    run = f'v{version}/' if version is not None else ''
    kept = f'v{keep}/' if keep is not None else None
    prefixes = [
        f'{PROCESSED_PREFIX}{kind}/{reel_id}/{run}' for kind in ('videos', 'images', 'thumbnails')
    ]
    try:
        if settings.S3_BUCKET_NAME:
            import boto3

            s3_kwargs = {
                'aws_access_key_id': settings.S3_ACCESS_KEY_ID,
                'aws_secret_access_key': settings.S3_SECRET_ACCESS_KEY,
                'region_name': settings.S3_REGION_NAME,
            }
            if settings.S3_ENDPOINT_URL:
                s3_kwargs['endpoint_url'] = settings.S3_ENDPOINT_URL
            s3 = boto3.client('s3', **s3_kwargs)
            removed = 0
            for prefix in prefixes:
                # ListObjects (v1), not V2. Every deletion in the system depends
                # on this call, and Ethio Telecom's OBS answers V2 with
                # NoSuchKey -- which this function then swallowed, so nothing
                # was ever deleted and the bucket filled up. Paginated for the
                # same reason a single call was wrong: it saw only the first
                # 1000 objects, and a post with several runs can exceed that.
                batch = []
                pages = s3.get_paginator('list_objects').paginate(
                    Bucket=settings.S3_BUCKET_NAME, Prefix=prefix
                )
                for page in pages:
                    for obj in page.get('Contents', []):
                        if kept and obj['Key'][len(prefix) :].startswith(kept):
                            continue
                        batch.append({'Key': obj['Key']})
                        if len(batch) == 1000:  # the API's own limit per call
                            s3.delete_objects(
                                Bucket=settings.S3_BUCKET_NAME, Delete={'Objects': batch}
                            )
                            removed += len(batch)
                            batch = []
                if batch:
                    s3.delete_objects(Bucket=settings.S3_BUCKET_NAME, Delete={'Objects': batch})
                    removed += len(batch)
            logger.info('[TASKS] removed %s stored objects of reel %s', removed, reel_id)
        else:
            for prefix in prefixes:
                base = os.path.join(settings.MEDIA_ROOT, prefix)
                if kept is None:
                    shutil.rmtree(base, ignore_errors=True)
                elif os.path.isdir(base):
                    for entry in os.listdir(base):
                        if f'{entry}/' != kept:
                            shutil.rmtree(os.path.join(base, entry), ignore_errors=True)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning('[TASKS] could not remove %s outputs of reel %s: %s', run, reel_id, exc)


# -- Thumbnail generation ----------------------------------------------------

# Portrait 9:20. Reels are shot portrait, so a portrait thumbnail fills the
# card without letterboxing.
THUMB_WIDTH = 320
THUMB_HEIGHT = 720


def _render_thumbnail(source_path, out_path):
    """
    Produce a THUMB_WIDTH x THUMB_HEIGHT JPEG from any still image.

    Scale-to-fill then centre-crop, rather than a plain resize. Resizing
    straight to a fixed pair of dimensions stretches anything whose aspect
    ratio is not 9:20 -- which is every landscape upload -- so faces come out
    visibly distorted. Cover-cropping keeps geometry correct and gives up
    edges instead, which is what a thumbnail can afford to lose.

    Upscaling is allowed: a source smaller than the target still has to fill
    the frame, and LANCZOS handles that enlargement without obvious softness.

    Returns out_path, or None when the source cannot be read.
    """
    from PIL import Image, ImageOps

    try:
        with Image.open(source_path) as img:
            # EXIF orientation first. Phone photos are often stored rotated
            # with the correction only in metadata; cropping before applying
            # it crops the wrong edges.
            img = ImageOps.exif_transpose(img)
            img = img.convert('RGB')

            # ImageOps.fit scales and centre-crops in one pass and picks the
            # correct axis itself, so portrait and landscape need no branches.
            thumb = ImageOps.fit(
                img,
                (THUMB_WIDTH, THUMB_HEIGHT),
                method=Image.LANCZOS,
                centering=(0.5, 0.5),
            )
            # quality=88 rather than the 85 used for full images: a thumbnail
            # is small enough that the extra bytes are negligible, and it is
            # shown near 1:1 where artefacts would be visible.
            thumb.save(out_path, 'JPEG', quality=88, optimize=True, progressive=True)
        return out_path
    except Exception as e:
        logger.warning('[TASKS] Thumbnail render failed for %s: %s', source_path, e)
        return None


# ── Video processing ─────────────────────────────────────────────────────────


#: The transcode ladder, smallest first: (field, rung, CRF).
#:
#: The rung is the SHORT side of the frame. "720p" is 720x1280 for the
#: vertical video this feed is made of, and 1280x720 for landscape; scaling by
#: height alone made a portrait 720p rung 405x720, a quarter of the pixels of
#: what the name promises.
#:
#: 360p and 480p exist for the audience this app actually has: Ethiopian
#: mobile data, where a 720p file is frequently the difference between a video
#: that plays and one that buffers to a stop. The CRF rises as the frame
#: shrinks -- a small frame tolerates more compression before artefacts show,
#: and the point of the rung is bytes, not fidelity.
#:
#: 1080p is deliberately absent. The source is phone video, the feed renders
#: at most a phone-width column, and a 1080p rung would cost storage and
#: encode time to serve pixels nobody sees.
VIDEO_LADDER = (
    ('media_360', 360, 30),
    ('media_480', 480, 28),
    ('media_720', 720, 23),
)

#: Peak bitrate per rung (VBV). CRF alone lets a busy scene spike far above
#: what a 3G link sustains; the cap keeps every second streamable.
VIDEO_MAXRATE = {360: '800k', 480: '1200k', 720: '2500k'}

#: Image widths, smallest first. Same reasoning as the video ladder: the
#: full-size still is often over a megabyte, and a feed column is at most a
#: phone wide. `thumbnail` is a 320x720 CROP for posters and cards; these keep
#: the source aspect ratio, so they can stand in for the post body itself.
IMAGE_LADDER = (
    ('image_small', 360),
    ('image_medium', 720),
)

#: WebP quality. Around 80 WebP matches the JPEG q82-85 used above at roughly
#: two thirds of the bytes; below that, faces and skin tones start to band.
WEBP_QUALITY = 80


def _rotation(stream):
    """Display rotation of a video stream in degrees (phones record rotated)."""
    for side in stream.get('side_data_list') or []:
        if 'rotation' in side:
            try:
                return int(float(side['rotation']))
            except (TypeError, ValueError):
                pass
    try:
        return int((stream.get('tags') or {}).get('rotate', 0))
    except (TypeError, ValueError):
        return 0


def _probe(path):
    """Display size, duration and audio presence of a video, via ffprobe."""
    import ffmpeg

    info = ffmpeg.probe(path)
    streams = info.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'), None)
    if not video:
        raise _Permanent('invalid_media')
    width, height = int(video.get('width') or 0), int(video.get('height') or 0)
    # ffmpeg applies the rotation when it decodes, so the frame the scaler
    # sees is the displayed one. Decide orientation on the same basis.
    rotation = _rotation(video)
    if abs(rotation) % 180 == 90:
        width, height = height, width
    try:
        duration = float(info.get('format', {}).get('duration') or video.get('duration') or 0)
    except (TypeError, ValueError):
        duration = 0.0
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), None)
    try:
        num, den = (video.get('avg_frame_rate') or '0/1').split('/')
        fps = float(num) / float(den) if float(den) else 0.0
    except (TypeError, ValueError):
        fps = 0.0
    return {
        'width': width,
        'height': height,
        'duration': duration,
        'has_audio': audio is not None,
        # What _can_serve_as_is needs to know about the upload's own streams.
        'vcodec': video.get('codec_name'),
        'pix_fmt': video.get('pix_fmt'),
        'acodec': audio.get('codec_name') if audio else None,
        'fps': fps,
        'rotation': rotation,
        'format_name': info.get('format', {}).get('format_name') or '',
    }


def _can_serve_as_is(info):
    """Whether the upload's own streams are what every browser plays: H.264,
    8-bit 4:2:0, AAC or silent, upright, at most 30 fps, in an MP4/MOV."""
    return (
        info.get('vcodec') == 'h264'
        and info.get('pix_fmt') in ('yuv420p', 'yuvj420p')
        and info.get('acodec') in (None, 'aac')
        and not info.get('rotation')
        and 0 < (info.get('fps') or 0) <= 30.5
        and 'mp4' in (info.get('format_name') or '')
    )


def _remux(input_path, out_path, has_audio):
    """The upload's streams, untouched, re-wrapped for streaming: index first
    (faststart), metadata and chapters dropped (GPS included). Returns the
    path, or None if it could not be written."""
    import ffmpeg

    try:
        source = ffmpeg.input(input_path)
        streams = [source['v:0']] + ([source['a:0']] if has_audio else [])
        (
            ffmpeg.output(
                *streams,
                out_path,
                c='copy',
                movflags='+faststart',
                map_metadata='-1',
                map_chapters='-1',
            )
            .overwrite_output()
            .run(quiet=True)
        )
        return out_path
    except Exception as exc:
        logger.warning('[TASKS] remux failed: %s', exc)
        return None


def _scale_filter(width, height, rung):
    """Scale so the frame's short side is ``rung``, keeping its aspect ratio.

    -2 rounds the other side to an even number, which H.264 requires; the
    picture is never stretched or cropped.
    """
    if width <= height:
        return f'scale={rung}:-2'
    return f'scale=-2:{rung}'


def _run_ffmpeg(stream, on_progress=None, duration=0.0):
    """Run an ffmpeg-python stream to completion.

    With ``on_progress`` and a known ``duration`` it reports the fraction
    encoded as FFmpeg itself counts it (``-progress``: the timestamp written so
    far over the clip's length). Without either it runs as before. Raises on
    a non-zero exit, with the tail of FFmpeg's error output.
    """
    import subprocess  # noqa: S404 - FFmpeg is the worker's job

    if not on_progress or not duration or duration <= 0:
        stream.run(quiet=True)
        return
    # A report every quarter second (FFmpeg's default is half): enough for a
    # short clip's bar to move visibly, trivial next to the encode itself.
    args = stream.global_args('-progress', 'pipe:1', '-nostats', '-stats_period', '0.25').compile()
    total_us = duration * 1_000_000
    with tempfile.TemporaryFile() as errors:
        # Arguments are built by ffmpeg-python from fixed options and paths in
        # the worker's own temporary directory.
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors)  # noqa: S603
        for raw in proc.stdout:
            key, _, value = raw.decode('ascii', 'replace').strip().partition('=')
            # out_time_ms is microseconds too, despite its name (FFmpeg keeps
            # it for compatibility); out_time_us is the newer spelling.
            if key in ('out_time_us', 'out_time_ms') and value.isdigit():
                on_progress(int(value) / total_us)
        proc.wait()
        if proc.returncode:
            errors.seek(0)
            raise RuntimeError(errors.read()[-800:].decode('utf-8', 'replace'))


def _transcode(
    input_path,
    out_path,
    height,
    crf,
    width=None,
    source_height=None,
    on_progress=None,
    duration=0.0,
):
    """One rung of the ladder. Returns the path, or None if encoding failed.

    ``height`` is the rung (short side). With the source's display size it
    scales portrait and landscape correctly; without it, it falls back to the
    old height-only scale. ``on_progress`` gets the fraction of this rung
    encoded, from FFmpeg's own progress output (see _run_ffmpeg).

    A failed rung is not fatal: the caller keeps whichever rungs succeeded, and
    the API simply does not advertise the missing one. Losing 360p is worth far
    less than losing the post.
    """
    import ffmpeg

    if width and source_height:
        vf = _scale_filter(width, source_height, height)
    else:
        vf = f'scale=-2:{height}'
    maxrate = VIDEO_MAXRATE.get(height, '2500k')
    try:
        stream = (
            ffmpeg.input(input_path)
            .output(
                out_path,
                vcodec='libx264',
                acodec='aac',
                vf=vf,
                crf=crf,
                preset='fast',
                maxrate=maxrate,
                bufsize=f'{int(maxrate[:-1]) * 2}k',
                # 4:2:0 High profile plays on every phone of the last decade;
                # a 4:4:4 or 10-bit source passed through untouched would not.
                pix_fmt='yuv420p',
                **{'profile:v': 'high', 'level:v': '4.0'},
                # 60fps phone footage gains little in a feed and costs bits.
                fpsmax=30,
                ac=2,
                # Moves the index to the front so a player can start on the
                # first bytes instead of seeking to the end first -- the single
                # most important flag for progressive playback.
                movflags='+faststart',
                # Container metadata carries GPS and device details. The
                # original is private; the served copy must not leak them.
                map_metadata='-1',
                map_chapters='-1',
                # Caps the audio too; 128k stereo on a 360p rung is a waste.
                audio_bitrate='96k' if height <= 480 else '128k',
            )
            .overwrite_output()
        )
        _run_ffmpeg(stream, on_progress, duration)
        return out_path
    except Exception as exc:
        logger.warning('[TASKS] %sp transcode failed: %s', height, exc)
        return None


def _resize_image(input_path, out_path, width, fmt='JPEG'):
    """Width-constrained copy that never upscales. Returns the path or None.

    ``fmt`` is 'JPEG' (progressive, the fallback every client decodes) or
    'WEBP' (the smaller rendition for clients that can use it).
    """
    from PIL import Image, ImageOps

    try:
        with Image.open(input_path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')

            # A source narrower than the target is left alone: enlarging adds
            # bytes without adding detail, and the caller can serve the
            # original instead.
            if img.width <= width:
                return None

            height = round(img.height * (width / img.width))
            img = img.resize((width, height), Image.LANCZOS)
            if fmt == 'WEBP':
                img.save(out_path, 'WEBP', quality=WEBP_QUALITY - 2, method=4)
            else:
                img.save(out_path, 'JPEG', quality=82, optimize=True, progressive=True)
        return out_path
    except Exception as exc:
        logger.warning('[TASKS] %spx image variant failed: %s', width, exc)
        return None


def _process_video(input_path, reel_id, workdir=None, info=None, on_progress=None):
    """Transcode the ladder and extract a thumbnail.

    Returns (primary_path, thumb_path, duration, variants) where ``variants``
    maps ladder fields to local paths. ``on_progress`` gets the fraction of
    the whole ladder encoded: each rung's share is its pixel count (a 720p
    frame is four times the work of a 360p one), filled in as FFmpeg reports
    that rung's progress.
    """
    import ffmpeg

    workdir = workdir or tempfile.mkdtemp(prefix=f'reel{reel_id}-')
    info = info or _probe(input_path)
    width, height = info['width'], info['height']
    short_side = min(width, height) if width and height else 0
    clip_seconds = info.get('duration') or 0.0

    planned = [
        rung for _field, rung, _crf in VIDEO_LADDER if not (short_side and rung > short_side)
    ]
    if not planned and short_side:
        planned = [short_side - (short_side % 2)]
    total_weight = sum(rung * rung for rung in planned) or 1
    encoded_weight = 0

    def encode(path, rung, crf):
        nonlocal encoded_weight
        share = rung * rung / total_weight
        done_before = encoded_weight / total_weight
        report = None
        if on_progress:

            def report(fraction):
                on_progress(done_before + share * max(0.0, min(1.0, fraction)))

        result = _transcode(
            input_path,
            path,
            rung,
            crf,
            width=width,
            source_height=height,
            on_progress=report,
            duration=clip_seconds,
        )
        encoded_weight += rung * rung
        if on_progress:
            on_progress(encoded_weight / total_weight, force=True)
        return result

    source_size = os.path.getsize(input_path)

    def keep_smaller(path, rung):
        # A rung at the upload's own size that came out no smaller than the
        # upload: re-encoding cost quality and saved nothing (an efficient
        # 720p H.264 file does this). When the upload is already what
        # browsers play, serve its own streams re-wrapped instead -- same
        # picture, no larger. Anything else (VP8/VP9, HEVC, 10-bit, rotated)
        # keeps the encode: playing everywhere outweighs the bytes.
        if rung != short_side or os.path.getsize(path) < source_size:
            return
        if not _can_serve_as_is(info):
            return
        copied = _remux(input_path, f'{path}.copy.mp4', info.get('has_audio', True))
        if copied and os.path.getsize(copied) < os.path.getsize(path):
            os.replace(copied, path)
            logger.info('media.passthrough rung=%sp source_bytes=%s', rung, source_size)

    # Never upscale. A 480p source re-encoded to 720p is larger, slower and
    # no sharper -- the rung is skipped rather than manufactured.
    variants = {}
    for field, rung, crf in VIDEO_LADDER:
        if short_side and rung > short_side:
            continue
        path = os.path.join(workdir, f'{rung}p.mp4')
        if encode(path, rung, crf):
            keep_smaller(path, rung)
            variants[field] = path

    # A source smaller than the lowest rung still has to play: one encode at
    # its own size (rounded to even), with the same codec settings.
    if not variants and short_side:
        native = short_side - (short_side % 2)
        path = os.path.join(workdir, f'{native}p.mp4')
        if encode(path, native, VIDEO_LADDER[0][2]):
            keep_smaller(path, native)
            variants['media_native'] = path

    # 720p is what `media` has always pointed at and what every existing client
    # requests, so it stays the primary. If the ladder produced nothing above
    # 360p -- a very small source, or failed encodes -- the largest that did
    # succeed takes its place rather than leaving the post unplayable.
    out_video = (
        variants.get('media_720')
        or variants.get('media_480')
        or variants.get('media_360')
        or variants.get('media_native')
    )
    if not out_video:
        raise RuntimeError(f'no video rung encoded for reel {reel_id}')

    # Duration from the encoded file: MediaRecorder WebM often carries none.
    duration = info['duration']
    try:
        encoded = float(ffmpeg.probe(out_video).get('format', {}).get('duration') or 0)
        if encoded > 0:
            duration = encoded
    except Exception as exc:  # pragma: no cover - the probe of our own output
        logger.debug('[TASKS] could not probe the encode for reel %s: %s', reel_id, exc)

    # Seek 10% in (capped at 1s) rather than frame 0: the opening frame of a
    # phone recording is often black or mid-autofocus. Taken from the encoded
    # primary: already the right way up, and far quicker to seek.
    seek = min(1.0, duration * 0.1) if duration > 0 else 0
    raw_frame = os.path.join(workdir, 'frame.jpg')
    out_thumb = os.path.join(workdir, 'thumb.jpg')
    try:
        (
            ffmpeg.input(out_video, ss=seek)
            .output(raw_frame, vframes=1, format='image2', vcodec='mjpeg')
            .overwrite_output()
            .run(quiet=True)
        )
    except Exception as exc:
        logger.warning('[TASKS] frame grab failed for reel %s: %s', reel_id, exc)

    # Crop the extracted frame to the thumbnail target. Done in Pillow rather
    # than as an ffmpeg scale filter so video and image uploads share one
    # implementation of the aspect/crop rules.
    if not os.path.exists(raw_frame) or _render_thumbnail(raw_frame, out_thumb) is None:
        out_thumb = None

    return out_video, out_thumb, duration, variants


def _process_image(input_path, out_path, max_px=1080, fmt='JPEG'):
    """
    Write an optimised copy of the image to out_path.

    Deliberately not in place. The previous version saved over the upload, so
    the original was destroyed the first time the task ran and a re-run
    re-compressed already-compressed output. Downscaling only happens when the
    source exceeds max_px -- a smaller image is copied at quality 85 rather
    than enlarged. EXIF (GPS included) is not carried over: Pillow writes none
    unless asked to.
    """
    from PIL import Image, ImageOps

    try:
        with Image.open(input_path) as img:
            img = ImageOps.exif_transpose(img)
            if fmt == 'WEBP' and img.mode in ('RGBA', 'LA'):
                img = img.convert('RGBA')  # WebP keeps transparency
            else:
                img = img.convert('RGB')
            if img.width > max_px or img.height > max_px:
                img.thumbnail((max_px, max_px), Image.LANCZOS)
            if fmt == 'WEBP':
                img.save(out_path, 'WEBP', quality=WEBP_QUALITY, method=4)
            else:
                img.save(out_path, 'JPEG', quality=85, optimize=True, progressive=True)
        return out_path
    except Exception as e:
        logger.warning('[TASKS] Image optimize error: %s', e)
        return None


#: A WebP is kept only when it is at least this much smaller than its JPEG.
#: A few percent does not pay for a second object in storage and a second
#: file for browsers to choose between.
WEBP_MIN_SAVING = 0.10


def _keep_webp(webp_path, jpg_path):
    """The WebP rendition, if it is worth serving; otherwise None.

    WebP is the smaller format for photographs but not for everything -- fine
    grain, flat graphics -- and a client told to prefer it would then download
    more, not less. Kept only when it saves at least WEBP_MIN_SAVING against
    the JPEG of the same size.
    """
    if not webp_path or not os.path.exists(webp_path):
        return None
    if jpg_path and os.path.exists(jpg_path):
        limit = os.path.getsize(jpg_path) * (1 - WEBP_MIN_SAVING)
        if os.path.getsize(webp_path) > limit:
            return None
    return webp_path


def _write_reel_fields(reel_pk, **fields):
    """
    Update reel fields without loading or saving the model.

    queryset.update() rather than the hand-built UPDATE this used to run: it
    issues the same single statement with no signals and no full-row write,
    but the column names go through the ORM instead of an f-string, so a
    caller cannot inject SQL through a keyword argument.
    """
    from api.models import Reel

    Reel.objects.filter(pk=reel_pk).update(**fields)


# ── Main reel processing task ────────────────────────────────────────────────

SOURCE_PREFIX = 'source/'
PROCESSED_PREFIX = 'processed/'

#: A hold older than this belongs to a worker that died mid-run.
STALE_CLAIM = timedelta(minutes=30)


class _Permanent(Exception):
    """A failure no retry can fix: bad input, or a rule the post breaks."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class _StorageWriteFailed(RuntimeError):
    """The encode worked but object storage refused the result. Retried like
    any transient error; if it outlasts the retries the post records
    `storage_write_failed` rather than a generic failure, since the cause is
    configuration or OBS, not the upload -- and the reason is in the
    '[TASKS] S3/OBS upload failed' warning just before it."""


def _claim(reel_id, task_id, force):
    """Take the post for this task, or say why not.

    One post is processed by one task at a time. A Celery retry keeps the same
    task id and so keeps its hold; a second task for the same post -- a double
    enqueue, a re-drive racing a slow worker -- finds it held and stops. A
    hold older than STALE_CLAIM is abandoned and may be taken over.
    """
    from api.models import MediaStatus, Reel

    try:
        reel = Reel.objects.get(pk=reel_id)
    except Reel.DoesNotExist:
        return None, 'not found'

    status = reel.processing_status
    if status == MediaStatus.READY and reel.processed_at and not force:
        return None, 'already processed'
    if status == MediaStatus.FAILED and not force:
        return None, 'failed; re-queue with force to try again'

    now = timezone.now()
    free = (
        Q(processing_task_id='')
        | Q(processing_task_id=task_id)
        | Q(processing_started_at__lt=now - STALE_CLAIM)
        | Q(processing_started_at__isnull=True)
    )
    claim = {'processing_task_id': task_id, 'processing_started_at': now}
    if status != MediaStatus.READY:
        # Each run reports its own progress from the start: a retry re-does
        # the work, and saying so is the honest number.
        claim['processing_progress'] = 0
    if status == MediaStatus.FAILED:
        claim['processing_status'] = MediaStatus.PROCESSING
    if not Reel.objects.filter(pk=reel_id).filter(free).update(**claim):
        return None, 'held by another task'
    reel.refresh_from_db()
    return reel, None


def _video_too_long(duration, user=None) -> bool:
    """Is a measured duration beyond what this poster may post?

    The limit is now per-user: 60 seconds on a subscription alone, 120 once
    coins have been bought (api/services/video_limits.py). It used to be
    ``settings.MEDIA_MAX_VIDEO_SECONDS`` for everybody, so a standard
    subscriber could post the full two minutes.

    That setting is still the ceiling nobody exceeds -- video_limits caps
    every entitlement to it -- so a deployment that lowers it still lowers
    it for all. Passing no user falls back to it, which is what a backfill
    of old posts wants: the rule that applied when they were published.

    Inclusive of the limit: 60.0 seconds is accepted for a standard
    subscriber and 60.01 is not, matching the pricing boundary so that "60
    seconds" means one thing across the product.

    Named rather than written twice inline, because it is checked before and
    after encoding and those two must not drift apart.
    """
    if not duration:
        return False

    if user is None:
        try:
            return float(duration) > settings.MEDIA_MAX_VIDEO_SECONDS
        except (TypeError, ValueError):
            return False

    from api.services import video_limits

    return video_limits.exceeds_limit(duration, user)


def _charge_long_video(reel, duration):
    """Charge the long-video difference once, now that the length is known.

    The upload request used to run ffprobe to decide this before answering;
    the worker is where the real duration is measured, so the charge moved
    here -- which is also why a client cannot buy a cheap long video by
    claiming a short duration. `long_video_charged` records it in the same
    transaction as the debit, so a retry of this task cannot charge twice. A
    user who cannot pay gets a failed post rather than a free long video.

    The band comes from api/services/post_pricing.py, shared with the request
    that charged the base price. It is inclusive of 60 seconds: a 60.0-second
    video is a long video, where this function previously charged it as short.
    """
    from django.db import transaction

    from api.models import Reel
    from api.models.contest import UserCoinBalance
    from api.models.wallet import WalletConfig
    from api.services import post_pricing

    if reel.long_video_charged or not post_pricing.is_long_video(duration):
        return
    # A photo has no duration and must never reach the video price, whatever
    # a caller passes. The video path is the only caller today; this keeps the
    # rule true of the function rather than of its call sites.
    if not (reel.original_media or reel.media):
        return
    config = WalletConfig.get_config()
    cost = post_pricing.long_video_extra(config, is_campaign_post=reel.is_campaign_post)
    if not cost:
        return
    with transaction.atomic():
        if not Reel.objects.filter(pk=reel.pk, long_video_charged=0).update(
            long_video_charged=cost
        ):
            return
        balance, _ = UserCoinBalance.objects.get_or_create(user=reel.user)
        try:
            balance.spend_coins(
                cost,
                'post_long_video',
                description=f'Video {post_pricing.LONG_VIDEO_SECONDS}s or longer (post {reel.pk})',
            )
        except ValueError as exc:
            raise _Permanent('long_video_unpaid') from exc


def _publisher(paths, on_progress):
    """``publish(path, key)`` -- _publish, reporting the share of these files'
    bytes stored so far. Sizes are taken up front: without object storage,
    publishing moves each file out of the work directory."""
    sizes = {path: os.path.getsize(path) for path in paths if path and os.path.exists(path)}
    total = sum(sizes.values()) or 1
    stored = 0

    def publish(path, key):
        nonlocal stored
        url = _publish(path, key)
        stored += sizes.get(path, 0)
        on_progress(stored / total)
        return url

    return publish


# Where each stage of a run sits in the 0-100 the author sees. Encoding is
# nearly all of a video's time; a photo's is mostly the upload of its outputs.
VIDEO_STAGES = {'fetch': (0, 5), 'probe': 6, 'encode': (6, 92), 'store': (92, 99)}
IMAGE_STAGES = {'fetch': (0, 10), 'render': (10, 50), 'store': (50, 99)}


def _run_video(reel, version, workdir, live, progress=_NO_PROGRESS):
    source_value = reel.original_media or str(reel.media or '')
    ext = os.path.splitext(source_value.split('?', 1)[0])[1] or '.mp4'
    input_path = _fetch_source(
        source_value,
        workdir,
        ext,
        on_progress=progress.span(*VIDEO_STAGES['fetch']),
        total=reel.source_size,
    )
    if not input_path or not os.path.exists(input_path):
        raise _Permanent('source_missing')

    try:
        info = _probe(input_path)
    except _Permanent:
        raise
    except Exception as exc:
        raise _Permanent('invalid_media') from exc
    progress.to(VIDEO_STAGES['probe'], force=True)

    # Rules that apply to a new upload, never to a post already published
    # (a backfill of old posts must not re-charge or reject them).
    if not live and _video_too_long(info['duration'], reel.user):
        raise _Permanent('video_too_long')

    out_video, out_thumb, duration, variants = _process_video(
        input_path, reel.pk, workdir, info, on_progress=progress.span(*VIDEO_STAGES['encode'])
    )

    if not live:
        if _video_too_long(duration, reel.user):
            raise _Permanent('video_too_long')
        _charge_long_video(reel, duration)

    base = f'{PROCESSED_PREFIX}videos/{reel.pk}/v{version}'
    # Measured before publishing: without object storage, publishing moves
    # the file out of the work directory.
    primary_size = os.path.getsize(out_video)
    extra_rungs = [
        variants[field]
        for field, _rung, _crf in VIDEO_LADDER
        if field != 'media_720' and field in variants and variants[field] != out_video
    ]
    publish = _publisher(
        [out_video, out_thumb, *extra_rungs], progress.span(*VIDEO_STAGES['store'])
    )
    primary_url = publish(out_video, f'{base}/{os.path.basename(out_video)}')
    if not primary_url:
        raise _StorageWriteFailed('primary rendition could not be stored')
    fields = {
        'media': primary_url,
        'duration': duration,
        'processed_size': primary_size,
        'media_360': '',
        'media_480': '',
    }
    if out_thumb:
        fields['thumbnail'] = (
            publish(out_thumb, f'{PROCESSED_PREFIX}thumbnails/{reel.pk}/v{version}/thumb.jpg') or ''
        )
    for field, rung, _crf in VIDEO_LADDER:
        if field in ('media_720',) or field not in variants:
            continue
        # The primary may itself be the 480p or 360p rung on a small source.
        if variants[field] == out_video:
            fields[field] = primary_url
            continue
        url = publish(variants[field], f'{base}/{rung}p.mp4')
        if url:
            fields[field] = url
    if not reel.original_media:
        fields['original_media'] = source_value
    return fields


def _run_image(reel, version, workdir, live, progress=_NO_PROGRESS):
    source_value = reel.original_image or str(reel.image or '')
    ext = os.path.splitext(source_value.split('?', 1)[0])[1] or '.jpg'
    input_path = _fetch_source(
        source_value,
        workdir,
        ext,
        on_progress=progress.span(*IMAGE_STAGES['fetch']),
        total=reel.source_size,
    )
    if not input_path or not os.path.exists(input_path):
        raise _Permanent('source_missing')

    # Every output first, then every upload: the uploads can then report the
    # share of all their bytes stored.
    rendered = progress.span(*IMAGE_STAGES['render'])
    full_jpg = _process_image(input_path, os.path.join(workdir, 'full.jpg'))
    if full_jpg is None:
        raise _Permanent('invalid_media')
    full_webp = _keep_webp(
        _process_image(input_path, os.path.join(workdir, 'full.webp'), fmt='WEBP'), full_jpg
    )
    thumb = _render_thumbnail(input_path, os.path.join(workdir, 'thumb.jpg'))
    rendered(0.5)

    # Width variants, generated from the SOURCE rather than from full.jpg --
    # resizing an already-recompressed JPEG stacks artefacts, and the source
    # is right here. Each WebP is compared with its JPEG before anything is
    # published, which may move the JPEG.
    widths = []
    for field, width in IMAGE_LADDER:
        jpg = _resize_image(input_path, os.path.join(workdir, f'{width}w.jpg'), width)
        webp = _keep_webp(
            _resize_image(input_path, os.path.join(workdir, f'{width}w.webp'), width, fmt='WEBP'),
            jpg,
        )
        widths.append((field, width, jpg, webp))
    rendered(1.0, force=True)

    base = f'{PROCESSED_PREFIX}images/{reel.pk}/v{version}'
    # Measured before publishing, which may move the files. The WebP is what
    # a modern client downloads, so it is the size that counts.
    jpg_size = os.path.getsize(full_jpg)
    webp_size = os.path.getsize(full_webp) if full_webp else None
    publish = _publisher(
        [full_jpg, full_webp, thumb, *(p for _f, _w, jpg, webp in widths for p in (jpg, webp))],
        progress.span(*IMAGE_STAGES['store']),
    )
    image_url = publish(full_jpg, f'{base}/full.jpg')
    if not image_url:
        raise _StorageWriteFailed('primary image could not be stored')
    fields = {
        'image': image_url,
        'image_webp': '',
        'image_small': '',
        'image_medium': '',
        'image_small_webp': '',
        'image_medium_webp': '',
        'processed_size': webp_size or jpg_size,
    }
    if full_webp:
        fields['image_webp'] = publish(full_webp, f'{base}/full.webp') or ''
    fields['thumbnail'] = (
        publish(thumb, f'{PROCESSED_PREFIX}thumbnails/{reel.pk}/v{version}/thumb.jpg')
        if thumb
        else None
    ) or image_url

    for field, width, jpg, webp in widths:
        if jpg:
            fields[field] = publish(jpg, f'{base}/{width}w.jpg') or ''
        if webp:
            fields[f'{field}_webp'] = publish(webp, f'{base}/{width}w.webp') or ''
    if not reel.original_image:
        fields['original_image'] = source_value
    return fields


def _is_video(reel):
    value = reel.original_media or str(reel.media or '')
    return bool(value)


def _finish(reel_id, task_id, **fields):
    """Write a run's outcome if the run still holds the post; False if not.

    A run can lose its hold while it works: it outlived STALE_CLAIM and a
    re-drive took over, or the post's media was replaced under it. Its outcome
    then describes media the post no longer has and must not overwrite the
    newer state.
    """
    from api.models import Reel

    return bool(Reel.objects.filter(pk=reel_id, processing_task_id=task_id).update(**fields))


def _give_up(reel_id, task_id, code, live):
    """Record a final failure. A post that was already being served keeps
    serving what it had -- only a new upload becomes FAILED."""
    from api.models import MediaStatus

    if live:
        written = _finish(reel_id, task_id, processing_failed=True, processing_task_id='')
    else:
        written = _finish(
            reel_id,
            task_id,
            processing_status=MediaStatus.FAILED,
            processing_error=code,
            processing_failed=True,
            processed=False,
            processing_task_id='',
        )
    logger.warning(
        'media.failed reel=%s code=%s live=%s%s',
        reel_id,
        code,
        live,
        '' if written else ' (superseded; not recorded)',
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60, acks_late=True)
def process_reel_media(self, reel_id, force=False):
    """Turn a post's original upload into what the feed serves.

    Videos: an H.264/AAC ladder (360p/480p/720p by short side, never upscaled,
    aspect kept) and a thumbnail. Images: an optimised JPEG and WebP, 360/720px
    width variants in both, a thumbnail; the blur placeholder follows.

    Idempotent: a post already processed by this pipeline is skipped unless
    ``force``; a second task for a post that is being processed stops; every
    run writes versioned keys, so a retry overwrites its own partial output
    and a re-process never rewrites objects clients have cached.

    Older posts that were published without processing (READY, never
    processed) are brought up to date in place when queued -- that is how the
    generate_missing_media backfill works -- and stay visible throughout.
    """
    from api.models import MediaStatus

    task_id = self.request.id or f'direct-{uuid.uuid4().hex}'
    reel, why = _claim(reel_id, task_id, force)
    if reel is None:
        return f'Reel {reel_id}: {why}'

    # A post that is already being served (an older post being backfilled, or
    # a forced re-process) stays READY on its current media until the new
    # media is in place.
    live = reel.processing_status == MediaStatus.READY
    version = reel.media_version + 1
    workdir = tempfile.mkdtemp(prefix=f'reel{reel_id}-')
    started = time.monotonic()
    # What the author's upload indicator shows (GET /posts/processing/).
    progress = _Progress(reel_id, task_id, enabled=not live)
    try:
        if _is_video(reel):
            kind, fields = 'video', _run_video(reel, version, workdir, live, progress)
        elif reel.original_image or str(reel.image or ''):
            kind, fields = 'image', _run_image(reel, version, workdir, live, progress)
        else:
            raise _Permanent('source_missing')

        finished = _finish(
            reel_id,
            task_id,
            **fields,
            processing_status=MediaStatus.READY,
            processing_progress=100,
            processing_error='',
            processed=True,
            processing_failed=False,
            processed_at=timezone.now(),
            media_version=version,
            processing_task_id='',
        )
        if not finished:
            logger.warning('media.superseded reel=%s version=%s', reel_id, version)
            return f'Reel {reel_id}: superseded'
        if reel.media_version:
            # Every earlier run's outputs, now that this one is in place: the
            # version it replaces, a replaced upload's media (kept until now,
            # so a post never loses its old files before the new ones exist),
            # and anything an abandoned run left. Keys are versioned, so
            # nothing a client is using is overwritten; this only removes
            # copies the post no longer refers to.
            _delete_version(reel_id, keep=version)

        # Always generate blurhash after processing
        generate_reel_blurhash.delay(reel_id)
        logger.info(
            'media.processed reel=%s kind=%s version=%s seconds=%.1f source_bytes=%s output_bytes=%s',
            reel_id,
            kind,
            version,
            time.monotonic() - started,
            reel.source_size,
            fields.get('processed_size'),
        )
        return f'Reel {reel_id} processed OK'

    except _Permanent as exc:
        _give_up(reel_id, task_id, exc.code, live)
        return f'Reel {reel_id} rejected: {exc.code}'
    except DataError:
        # The result does not fit the row (a value too long for its column).
        # Deterministic: every retry would re-encode the whole upload only to
        # fail on the same write, so it fails now, with its own code.
        logger.exception('[TASKS] process_reel_media could not record reel=%s', reel_id)
        _give_up(reel_id, task_id, 'record_failed', live)
        return f'Reel {reel_id} rejected: record_failed'
    except Exception as exc:
        logger.exception('[TASKS] process_reel_media error reel=%s', reel_id)
        # On the final attempt, record the failure. Without this a reel that
        # exhausted its retries is indistinguishable from one still queued.
        if self.request.retries >= self.max_retries:
            code = (
                'storage_write_failed'
                if isinstance(exc, _StorageWriteFailed)
                else 'processing_failed'
            )
            _give_up(reel_id, task_id, code, live)
            return f'Reel {reel_id} failed after retries'
        raise self.retry(exc=exc) from exc
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@shared_task
def redrive_stuck_media():
    """Re-queue posts whose processing never started or stopped mid-way.

    A post is created and its task queued after the transaction commits; if the
    broker was unreachable at that moment, or the worker died holding the
    post, nothing would ever pick it up. This finds both and queues them again
    -- the claim in process_reel_media makes a duplicate harmless.
    """
    from api.models import MediaStatus, Reel

    now = timezone.now()
    stuck = Reel.objects.filter(processing_status=MediaStatus.PROCESSING).filter(
        Q(processing_started_at__isnull=True, created_at__lt=now - timedelta(minutes=10))
        | Q(processing_started_at__lt=now - STALE_CLAIM)
    )
    ids = list(stuck.values_list('id', flat=True)[:200])
    for reel_id in ids:
        process_reel_media.delay(reel_id)
    return f'Re-queued {len(ids)} post(s)'


@shared_task(ignore_result=True)
def delete_post_media(reel_id, source_keys=(), versions=None):
    """Remove media a post no longer uses: private originals, and processed
    versions -- the listed ones, or every one when ``versions`` is None (the
    post was deleted). Queued once the change has committed; without it these
    stayed in the bucket forever, since nothing refers to them any more.
    """
    from api.services.media_pipeline import discard_source

    for key in source_keys or ():
        if key and key.startswith(SOURCE_PREFIX):
            discard_source(key)
    if versions is None:
        _delete_version(reel_id)
    else:
        for version in versions:
            _delete_version(reel_id, version)
    return f'Removed unused media of post {reel_id}'


@shared_task
def purge_processed_sources():
    """Delete originals of processed posts older than MEDIA_SOURCE_RETENTION_DAYS.

    Off by default (0 keeps everything). Only originals under source/ are ever
    touched -- older posts' media is not an original in that sense -- and only
    once the post is READY and its processed media is confirmed to exist.
    """
    from api.models import MediaStatus, Reel

    days = settings.MEDIA_SOURCE_RETENTION_DAYS
    if not days or days <= 0:
        return 'Retention disabled; originals are kept.'

    from api.services.media_pipeline import processed_media_exists, source_storage

    cutoff = timezone.now() - timedelta(days=days)
    candidates = Reel.objects.filter(
        processing_status=MediaStatus.READY,
        processed_at__lt=cutoff,
        source_deleted_at__isnull=True,
    ).filter(
        Q(original_media__startswith=SOURCE_PREFIX) | Q(original_image__startswith=SOURCE_PREFIX)
    )

    removed = 0
    for reel in candidates[:500]:
        key = (
            reel.original_media
            if reel.original_media.startswith(SOURCE_PREFIX)
            else reel.original_image
        )
        if not processed_media_exists(reel):
            logger.warning('media.retention skipped reel=%s: processed media not found', reel.pk)
            continue
        try:
            source_storage().delete(key)
        except Exception as exc:
            logger.warning('media.retention could not delete %s: %s', key, exc)
            continue
        _write_reel_fields(reel.pk, source_deleted_at=timezone.now())
        removed += 1
    return f'Removed {removed} original(s)'


# ── Blurhash ─────────────────────────────────────────────────────────────────


@shared_task
def generate_reel_blurhash(reel_id):
    """Generate blurhash string from reel thumbnail or image."""
    import blurhash
    from PIL import Image

    from api.models import Reel

    try:
        reel = Reel.objects.get(pk=reel_id)
    except Reel.DoesNotExist:
        return

    source = str(reel.thumbnail or '') or str(reel.image or '')
    if not source:
        return

    tmp = None
    try:
        if source.startswith('http'):
            tmp = _fetch_to_temp(source, '.jpg')
            img_path = tmp
        else:
            img_path = _local_path(source)

        if not img_path or not os.path.exists(img_path):
            return f'Reel {reel_id}: source image not found for blurhash'

        img = Image.open(img_path).convert('RGB')
        img.thumbnail((64, 64))
        hash_val = blurhash.encode(img, x_components=4, y_components=3)
        Reel.objects.filter(pk=reel_id).update(blurhash=hash_val)
        return f'Blurhash OK reel={reel_id}: {hash_val}'
    except Exception as e:
        return f'Blurhash error reel={reel_id}: {e}'
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


# ── Profile image optimisation ───────────────────────────────────────────────


@shared_task
def optimize_profile_image(user_id):
    """Resize and compress a user's profile photo."""
    from django.contrib.auth.models import User
    from PIL import Image

    try:
        profile = User.objects.select_related('profile').get(pk=user_id).profile
    except User.DoesNotExist:
        return

    if not profile.profile_photo:
        return

    try:
        path = profile.profile_photo.path
        img = Image.open(path).convert('RGB')
        img.thumbnail((400, 400), Image.LANCZOS)
        img.save(path, 'JPEG', quality=85, optimize=True)

        s3_url = _upload_to_s3(path, f'profile_photos/user_{user_id}.jpg')
        if s3_url:
            from django.db import connection

            with connection.cursor() as cur:
                cur.execute(
                    'UPDATE api_userprofile SET profile_photo=%s WHERE user_id=%s',
                    [s3_url, user_id],
                )
        return f'Profile photo optimised user={user_id}'
    except Exception as e:
        return f'Profile photo error user={user_id}: {e}'


# ── Push notifications (FCM) ─────────────────────────────────────────────────


@shared_task
def send_push_notification(user_id, message_data):
    """Send FCM push notification.

    Requires FIREBASE_SERVER_KEY, resolved through Django settings
    (environment -> Vault -> .env).
    """
    fcm_key = settings.FIREBASE_SERVER_KEY
    if not fcm_key:
        return 'FCM not configured — set FIREBASE_SERVER_KEY'

    try:
        from django.contrib.auth.models import User

        profile = User.objects.select_related('profile').get(pk=user_id).profile
        fcm_token = getattr(profile, 'fcm_token', '')
        if not fcm_token:
            return f'No FCM token for user {user_id}'

        resp = http_requests.post(
            'https://fcm.googleapis.com/fcm/send',
            json={
                'to': fcm_token,
                'notification': {
                    'title': message_data.get('title', 'FlipStar'),
                    'body': message_data.get('body', ''),
                    'sound': 'default',
                },
                'data': message_data.get('data', {}),
                'priority': 'high',
            },
            headers={
                'Authorization': f'key={fcm_key}',
                'Content-Type': 'application/json',
            },
            timeout=10,
        )
        return f'FCM sent user={user_id} status={resp.status_code}'
    except Exception as e:
        return f'FCM error user={user_id}: {e}'
