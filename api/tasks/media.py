import os
import tempfile

import redis
import requests as http_requests
from celery import shared_task
from django.conf import settings

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


def _upload_to_s3(local_path, s3_key):
    """Upload processed file to S3/MinIO and return public URL.

    Credentials come from Django settings (resolved via environment -> Vault ->
    .env), so the worker uses exactly the same values as the web process.
    """
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

        s3 = boto3.client('s3', **s3_kwargs)
        s3.upload_file(local_path, bucket, s3_key, ExtraArgs={'ACL': 'public-read'})

        if endpoint_url:
            return f'{endpoint_url}/{bucket}/{s3_key}'
        else:
            return f'https://{bucket}.s3.{region}.amazonaws.com/{s3_key}'
    except Exception as e:
        print(f'[TASKS] S3/MinIO upload failed: {e}')
        return None


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
        print(f'[TASKS] Thumbnail render failed for {source_path}: {e}')
        return None


# ── Video processing ─────────────────────────────────────────────────────────


def _process_video(input_path, reel_id):
    """Compress to 720p H.264/AAC, extract thumbnail, return (video_path, thumb_path, duration)."""
    import ffmpeg

    processed_dir = os.path.join(settings.MEDIA_ROOT, 'reels', 'processed')
    thumb_dir = os.path.join(settings.MEDIA_ROOT, 'thumbnails')
    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(thumb_dir, exist_ok=True)

    out_video = os.path.join(processed_dir, f'reel_{reel_id}_720p.mp4')
    out_thumb = os.path.join(thumb_dir, f'reel_{reel_id}_thumb.jpg')

    probe = ffmpeg.probe(input_path)
    duration = float(probe['format'].get('duration', 0))

    (
        ffmpeg.input(input_path)
        .output(
            out_video,
            vcodec='libx264',
            acodec='aac',
            vf='scale=-2:720',
            crf=23,
            preset='fast',
            movflags='faststart',
        )
        .overwrite_output()
        .run(quiet=True)
    )

    # Seek 10% in (capped at 1s) rather than frame 0: the opening frame of a
    # phone recording is often black or mid-autofocus.
    seek = min(1.0, duration * 0.1) if duration > 0 else 0
    raw_frame = os.path.join(thumb_dir, f'reel_{reel_id}_frame.jpg')
    (
        ffmpeg.input(input_path, ss=seek)
        .output(raw_frame, vframes=1, format='image2', vcodec='mjpeg')
        .overwrite_output()
        .run(quiet=True)
    )

    # Crop the extracted frame to the thumbnail target. Done in Pillow rather
    # than as an ffmpeg scale filter so video and image uploads share one
    # implementation of the aspect/crop rules.
    if _render_thumbnail(raw_frame, out_thumb) is None:
        out_thumb = None
    if os.path.exists(raw_frame):
        os.unlink(raw_frame)

    return out_video, out_thumb, duration


def _process_image(input_path, out_path, max_px=1080):
    """
    Write an optimised copy of the image to out_path.

    Deliberately not in place. The previous version saved over the upload, so
    the original was destroyed the first time the task ran and a re-run
    re-compressed already-compressed output. Downscaling only happens when the
    source exceeds max_px -- a smaller image is copied at quality 85 rather
    than enlarged.
    """
    from PIL import Image, ImageOps

    try:
        with Image.open(input_path) as img:
            img = ImageOps.exif_transpose(img).convert('RGB')
            if img.width > max_px or img.height > max_px:
                img.thumbnail((max_px, max_px), Image.LANCZOS)
            img.save(out_path, 'JPEG', quality=85, optimize=True, progressive=True)
        return out_path
    except Exception as e:
        print(f'[TASKS] Image optimize error: {e}')
        return None


def _publish(local_path, s3_key, discard=None):
    """Upload a generated artifact and return the URL to store for it.

    Appends to ``discard`` only when the upload actually succeeded. A file that
    never reached S3 is the one being served -- the caller falls back to its
    relative path -- so deleting it would leave the reel pointing at nothing.
    Pass ``discard=None`` for a path that must survive regardless, such as the
    source image reused when optimisation fails.
    """
    url = _upload_to_s3(local_path, s3_key)
    if url:
        if discard is not None:
            discard.append(local_path)
        return url
    return os.path.relpath(local_path, settings.MEDIA_ROOT)


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


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_reel_media(self, reel_id):
    """Process a reel's media after upload: compress video or optimise image, generate thumbnail."""
    from api.models import Reel

    try:
        reel = Reel.objects.get(pk=reel_id)
    except Reel.DoesNotExist:
        return f'Reel {reel_id} not found'

    media_val = str(reel.media or '').strip()
    image_val = str(reel.image or '').strip()
    tmp_file = None
    # Local copies of artifacts that reached S3. Kept until the end so a failure
    # mid-flow still cleans up whatever was already uploaded.
    discard = []

    try:
        if media_val:
            # ── Video flow ──
            if media_val.startswith('http'):
                tmp_file = _fetch_to_temp(media_val, '.mp4')
                input_path = tmp_file
            else:
                input_path = _local_path(media_val)

            if not input_path or not os.path.exists(input_path):
                return f'Reel {reel_id}: video file not accessible'

            out_video, out_thumb, duration = _process_video(input_path, reel_id)

            # Try S3 upload first; fall back to relative local path
            video_url = _publish(out_video, f'reels/processed/reel_{reel_id}_720p.mp4', discard)
            thumb_url = (
                _publish(out_thumb, f'thumbnails/reel_{reel_id}_thumb.jpg', discard)
                if out_thumb
                else ''
            )

            # original_media records where the untouched upload lives before
            # `media` is repointed at the transcode, so processing can be re-run
            # from source rather than from its own output.
            _write_reel_fields(
                reel_id,
                original_media=reel.original_media or media_val,
                media=video_url,
                thumbnail=thumb_url,
                duration=duration,
                processed=True,
                processing_failed=False,
            )

        elif image_val:
            # ── Image flow ──
            if image_val.startswith('http'):
                tmp_file = _fetch_to_temp(image_val, '.jpg')
                input_path = tmp_file
            else:
                input_path = _local_path(image_val)

            if not input_path or not os.path.exists(input_path):
                return f'Reel {reel_id}: image file not accessible'

            processed_dir = os.path.join(settings.MEDIA_ROOT, 'reels', 'processed')
            thumb_dir = os.path.join(settings.MEDIA_ROOT, 'thumbnails')
            os.makedirs(processed_dir, exist_ok=True)
            os.makedirs(thumb_dir, exist_ok=True)

            out_image = os.path.join(processed_dir, f'reel_{reel_id}.jpg')
            out_thumb = os.path.join(thumb_dir, f'reel_{reel_id}_thumb.jpg')

            if _process_image(input_path, out_image) is None:
                out_image = input_path  # optimisation failed; ship the source

            # A separately cropped thumbnail, not the full image reused. Serving
            # a 1080px still as a list thumbnail wastes bandwidth on every card.
            thumb_path = _render_thumbnail(input_path, out_thumb)

            # discard=None when optimisation fell back to the source: that path
            # is the untouched upload, not an artifact this task created.
            img_url = _publish(
                out_image,
                f'reels/reel_{reel_id}.jpg',
                discard if out_image != input_path else None,
            )
            thumb_url = (
                _publish(thumb_path, f'thumbnails/reel_{reel_id}_thumb.jpg', discard)
                if thumb_path
                else img_url
            )

            _write_reel_fields(
                reel_id,
                original_image=reel.original_image or image_val,
                image=img_url,
                thumbnail=thumb_url,
                processed=True,
                processing_failed=False,
            )

        else:
            return f'Reel {reel_id} has no media'

        # Always generate blurhash after processing
        generate_reel_blurhash.delay(reel_id)
        return f'Reel {reel_id} processed OK'

    except Exception as exc:
        print(f'[TASKS] process_reel_media error reel={reel_id}: {exc}')
        # On the final attempt, record the failure. Without this a reel that
        # exhausted its retries is indistinguishable from one still queued --
        # both are processed=False -- so nothing can report or re-drive it.
        if self.request.retries >= self.max_retries:
            _write_reel_fields(reel_id, processing_failed=True)
        raise self.retry(exc=exc) from exc
    finally:
        if tmp_file and os.path.exists(tmp_file):
            os.unlink(tmp_file)
        # Transcodes and thumbnails are written under MEDIA_ROOT before being
        # uploaded. Leaving them there filled the worker's disk: a 720p encode
        # per reel, never read again once the object store has it.
        for path in discard:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except OSError as exc:  # pragma: no cover - best effort
                print(f'[TASKS] could not remove artifact {path}: {exc}')


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
