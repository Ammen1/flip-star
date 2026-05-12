import os
import tempfile
import requests as http_requests
import redis
from io import BytesIO
from celery import shared_task
from django.conf import settings
from decouple import config

_redis = redis.Redis(
    host=config('REDIS_HOST', default='127.0.0.1'),
    port=int(config('REDIS_PORT', default=6379)),
    db=0,
)


# ── Presence cleanup ────────────────────────────────────────────────────────

@shared_task
def cleanup_typing_indicators():
    """Clean up expired typing indicators from Redis."""
    try:
        keys = _redis.keys('typing:*')
        return f"Found {len(keys)} active typing indicators"
    except Exception as e:
        return f"Error: {str(e)}"


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
    """Upload processed file to S3/MinIO and return public URL."""
    bucket = config('STORAGE_BUCKET_NAME', default='')
    endpoint_url = config('S3_ENDPOINT_URL', default='')
    region = config('REGION_NAME', default='us-east-1')
    if not bucket:
        return None
    try:
        import boto3
        s3_kwargs = {
            'aws_access_key_id': config('ACCESS_KEY_ID'),
            'aws_secret_access_key': config('SECRET_ACCESS_KEY'),
            'region_name': region,
        }
        if endpoint_url:
            s3_kwargs['endpoint_url'] = endpoint_url
        
        s3 = boto3.client('s3', **s3_kwargs)
        s3.upload_file(local_path, bucket, s3_key, ExtraArgs={'ACL': 'public-read'})
        
        if endpoint_url:
            return f"{endpoint_url}/{bucket}/{s3_key}"
        else:
            return f"https://{bucket}.s3.{region}.amazonaws.com/{s3_key}"
    except Exception as e:
        print(f"[TASKS] S3/MinIO upload failed: {e}")
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
        ffmpeg
        .input(input_path)
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

    seek = min(1.0, duration * 0.1) if duration > 0 else 0
    (
        ffmpeg
        .input(input_path, ss=seek)
        .output(out_thumb, vframes=1, format='image2', vcodec='mjpeg')
        .overwrite_output()
        .run(quiet=True)
    )

    return out_video, out_thumb, duration


def _process_image(input_path, max_px=1080):
    """Resize + compress image in-place, return path."""
    from PIL import Image
    try:
        img = Image.open(input_path).convert('RGB')
        if img.width > max_px or img.height > max_px:
            img.thumbnail((max_px, max_px), Image.LANCZOS)
        img.save(input_path, 'JPEG', quality=85, optimize=True)
    except Exception as e:
        print(f"[TASKS] Image optimize error: {e}")
    return input_path


def _write_reel_fields(reel_pk, **fields):
    """Update reel fields via raw SQL (same pattern as existing upload code)."""
    from django.db import connection
    set_clause = ', '.join(f"{k}=%s" for k in fields)
    values = list(fields.values()) + [reel_pk]
    with connection.cursor() as cur:
        cur.execute(f"UPDATE api_reel SET {set_clause} WHERE id=%s", values)


# ── Main reel processing task ────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_reel_media(self, reel_id):
    """Process a reel's media after upload: compress video or optimise image, generate thumbnail."""
    from api.models import Reel

    try:
        reel = Reel.objects.get(pk=reel_id)
    except Reel.DoesNotExist:
        return f"Reel {reel_id} not found"

    media_val = str(reel.media or '').strip()
    image_val = str(reel.image or '').strip()
    tmp_file = None

    try:
        if media_val:
            # ── Video flow ──
            if media_val.startswith('http'):
                tmp_file = _fetch_to_temp(media_val, '.mp4')
                input_path = tmp_file
            else:
                input_path = _local_path(media_val)

            if not input_path or not os.path.exists(input_path):
                return f"Reel {reel_id}: video file not accessible"

            out_video, out_thumb, duration = _process_video(input_path, reel_id)

            # Try S3 upload first; fall back to relative local path
            video_url = _upload_to_s3(out_video, f'reels/processed/reel_{reel_id}_720p.mp4') \
                        or os.path.relpath(out_video, settings.MEDIA_ROOT)
            thumb_url = _upload_to_s3(out_thumb, f'thumbnails/reel_{reel_id}_thumb.jpg') \
                        or os.path.relpath(out_thumb, settings.MEDIA_ROOT)

            _write_reel_fields(reel_id, media=video_url, thumbnail=thumb_url,
                               duration=duration, processed=True)

        elif image_val:
            # ── Image flow ──
            if image_val.startswith('http'):
                tmp_file = _fetch_to_temp(image_val, '.jpg')
                input_path = tmp_file
            else:
                input_path = _local_path(image_val)

            if not input_path or not os.path.exists(input_path):
                return f"Reel {reel_id}: image file not accessible"

            _process_image(input_path)

            img_url = _upload_to_s3(input_path, f'reels/reel_{reel_id}.jpg') or image_val
            _write_reel_fields(reel_id, image=img_url, thumbnail=img_url, processed=True)

        else:
            return f"Reel {reel_id} has no media"

        # Always generate blurhash after processing
        generate_reel_blurhash.delay(reel_id)
        return f"Reel {reel_id} processed OK"

    except Exception as exc:
        print(f"[TASKS] process_reel_media error reel={reel_id}: {exc}")
        raise self.retry(exc=exc)
    finally:
        if tmp_file and os.path.exists(tmp_file):
            os.unlink(tmp_file)


# ── Blurhash ─────────────────────────────────────────────────────────────────

@shared_task
def generate_reel_blurhash(reel_id):
    """Generate blurhash string from reel thumbnail or image."""
    from api.models import Reel
    from PIL import Image
    import blurhash

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
            return f"Reel {reel_id}: source image not found for blurhash"

        img = Image.open(img_path).convert('RGB')
        img.thumbnail((64, 64))
        hash_val = blurhash.encode(img, x_components=4, y_components=3)
        Reel.objects.filter(pk=reel_id).update(blurhash=hash_val)
        return f"Blurhash OK reel={reel_id}: {hash_val}"
    except Exception as e:
        return f"Blurhash error reel={reel_id}: {e}"
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
                    "UPDATE api_userprofile SET profile_photo=%s WHERE user_id=%s",
                    [s3_url, user_id]
                )
        return f"Profile photo optimised user={user_id}"
    except Exception as e:
        return f"Profile photo error user={user_id}: {e}"


# ── Push notifications (FCM) ─────────────────────────────────────────────────

@shared_task
def send_push_notification(user_id, message_data):
    """Send FCM push notification. Requires FIREBASE_SERVER_KEY in env."""
    fcm_key = config('FIREBASE_SERVER_KEY', default='')
    if not fcm_key:
        return "FCM not configured — set FIREBASE_SERVER_KEY"

    try:
        from django.contrib.auth.models import User
        profile = User.objects.select_related('profile').get(pk=user_id).profile
        fcm_token = getattr(profile, 'fcm_token', '')
        if not fcm_token:
            return f"No FCM token for user {user_id}"

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
        return f"FCM sent user={user_id} status={resp.status_code}"
    except Exception as e:
        return f"FCM error user={user_id}: {e}"
