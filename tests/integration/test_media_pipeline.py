"""
The media pipeline, from upload to READY, for every client.

What was wrong
--------------
/posts/create/ -- the endpoint both the web app and the Expo app upload to --
never queued processing. Every post from either client was published as its
raw upload: no transcode, no 360p/480p rungs, a frame grab for a thumbnail,
GPS metadata intact. The request also ran ffprobe and an FFmpeg frame grab
while the client waited, ignored the chosen category, created a second post
when a slow upload was retried, and returned Python tracebacks on error.

What these pin
--------------
  intake      the request stores the original privately and returns PROCESSING
              without running FFmpeg; the file's real type decides, not its name
  one path    /posts/create/, POST /reels/ and campaign posts share it
  category    saved and returned; unknown ones refused
  retries     one submission id, one post, one charge
  status      only READY media reaches feeds; the author sees the rest
  worker      images: JPEG + WebP, variants, thumbnail, orientation, no upscale
              videos: H.264/AAC ladder by short side, aspect kept, never
              upscaled, thumbnail, metadata stripped, faststart
  idempotent  a processed post is not processed again; a held post is not
              processed twice
  failure     permanent errors fail at once with a code; transient ones retry,
              then fail; an already-served post keeps serving
  retention   originals are only deleted, when enabled, after processing is
              confirmed
"""

import io
import os
import shutil
import subprocess
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import Category, MediaStatus, Reel
from api.tasks import media as media_tasks

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

factory = APIRequestFactory()

HAS_FFMPEG = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason='ffmpeg/ffprobe not installed')


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path / 'media')
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    settings.S3_BUCKET_NAME = ''
    return settings.MEDIA_ROOT


@pytest.fixture
def author():
    return User.objects.create_user(username='pipeline_author', password='x')


@pytest.fixture
def stranger():
    return User.objects.create_user(username='pipeline_stranger', password='x')


@pytest.fixture
def subscribed(monkeypatch):
    """Video posts are subscriber-only; that gate has its own tests."""
    import api.views.core as core

    monkeypatch.setattr(core, 'has_active_subscription', lambda user: True)


@pytest.fixture
def queued(monkeypatch):
    """What the request hands to the worker, without running it."""
    calls = []
    monkeypatch.setattr(
        media_tasks.process_reel_media, 'delay', lambda *a, **k: calls.append((a, k))
    )
    return calls


@pytest.fixture
def no_ffmpeg_in_request(monkeypatch):
    import ffmpeg

    def boom(*args, **kwargs):
        raise AssertionError('FFmpeg ran inside the HTTP request')

    monkeypatch.setattr(ffmpeg, 'probe', boom)
    monkeypatch.setattr(ffmpeg, 'input', boom)


def jpeg_bytes(width=64, height=48, color=(200, 80, 40), exif_orientation=None, noise=False):
    img = Image.new('RGB', (width, height), color)
    if noise:
        import random

        rnd = random.Random(width * height)  # noqa: S311 - test pixels, not secrets
        px = img.load()
        for x in range(0, width, 2):
            for y in range(0, height, 2):
                px[x, y] = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
    buf = io.BytesIO()
    kwargs = {'quality': 95}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kwargs['exif'] = exif.tobytes()
    img.save(buf, 'JPEG', **kwargs)
    return buf.getvalue()


def photo_bytes(width, height):
    """Shaped like a photograph -- gradients, soft edges, a little grain --
    rather than a flat colour or pure noise, neither of which any codec sees
    in practice."""
    import random

    from PIL import ImageDraw, ImageFilter

    ramp = Image.linear_gradient('L')
    img = Image.merge(
        'RGB',
        (
            ramp.resize((width, height)),
            ramp.rotate(90).resize((width, height)),
            ramp.transpose(Image.FLIP_TOP_BOTTOM).resize((width, height)),
        ),
    )
    draw = ImageDraw.Draw(img)
    rnd = random.Random(7)  # noqa: S311 - test pixels, not secrets
    for _ in range(40):
        x, y, r = rnd.randrange(width), rnd.randrange(height), rnd.randrange(20, 200)
        draw.ellipse(
            (x - r, y - r, x + r, y + r),
            fill=(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)),
        )
    img = img.filter(ImageFilter.GaussianBlur(2))
    img = Image.blend(img, Image.effect_noise((width, height), 40).convert('RGB'), 0.08)
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=95)
    return buf.getvalue()


def image_bytes(fmt, width=64, height=48, mode='RGB'):
    img = Image.new(mode, (width, height), (10, 150, 90, 128) if mode == 'RGBA' else (10, 150, 90))
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


MP4_HEADER = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 64
WEBM_HEADER = b'\x1a\x45\xdf\xa3' + b'\x00' * 20 + b'webm' + b'\x00' * 40
HEIC_HEADER = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 64


def upload(name, content, content_type='application/octet-stream'):
    return SimpleUploadedFile(name, content, content_type=content_type)


def create(user, file, view=None, headers=None, **data):
    from api.views.core import create_post

    request = factory.post('/posts/create/', {'file': file, **data}, **(headers or {}))
    force_authenticate(request, user=user)
    return (view or create_post)(request)


def list_reels(viewer=None, **params):
    from api.views.core import ReelViewSet

    request = factory.get('/reels/', params)
    if viewer is not None:
        force_authenticate(request, user=viewer)
    response = ReelViewSet.as_view({'get': 'list'})(request)
    data = response.data
    rows = data.get('results', data) if isinstance(data, dict) else data
    return {row['id']: row for row in rows}


def retrieve(user, pk):
    from api.views.core import ReelViewSet

    request = factory.get(f'/reels/{pk}/')
    if user is not None:
        force_authenticate(request, user=user)
    return ReelViewSet.as_view({'get': 'retrieve'})(request, pk=pk)


def process(reel, **kwargs):
    return media_tasks.process_reel_media.apply(args=[reel.pk], kwargs=kwargs).get()


def attempt(reel, number, task_id='task-1'):
    """One delivery of the task as the broker makes it: the same task id on
    every retry, with the retry count. (Eager mode would raise on the first
    retry rather than run the next one, so retries are driven here.)"""
    return media_tasks.process_reel_media.apply(
        args=[reel.pk], task_id=task_id, retries=number, throw=True
    )


def stored(key):
    from django.core.files.storage import default_storage

    return default_storage.exists(key)


# ---------------------------------------------------------------------------
# Intake: the request stores, records and returns -- no FFmpeg
# ---------------------------------------------------------------------------


def test_a_video_post_is_stored_privately_and_returned_processing(
    author, subscribed, queued, no_ffmpeg_in_request, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = create(author, upload('clip.mp4', MP4_HEADER, 'video/mp4'), caption='hello')

    assert response.status_code == 201, response.data
    data = response.data
    assert data['processing_status'] == 'PROCESSING'
    assert data['media_type'] == 'video'
    assert data['media'] is None, 'the original must not be served'
    assert data['thumbnail'] is None

    reel = Reel.objects.get(pk=data['id'])
    assert reel.original_media.startswith(f'source/videos/{author.pk}/')
    assert reel.original_media.endswith('.mp4')
    assert stored(reel.original_media)
    assert reel.source_size == len(MP4_HEADER)
    assert queued == [((reel.pk,), {})], 'processing was not queued'


def test_an_image_post_goes_through_the_same_path(
    author, queued, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = create(author, upload('photo.jpg', jpeg_bytes(), 'image/jpeg'))

    assert response.status_code == 201, response.data
    assert response.data['processing_status'] == 'PROCESSING'
    assert response.data['media_type'] == 'image'
    assert response.data['image'] is None
    reel = Reel.objects.get(pk=response.data['id'])
    assert reel.original_image.startswith(f'source/images/{author.pk}/')
    assert len(queued) == 1


def test_processing_is_queued_only_after_the_post_commits(author, queued):
    """The worker must never look for a post that does not exist yet."""
    response = create(author, upload('photo.jpg', jpeg_bytes(), 'image/jpeg'))

    assert response.status_code == 201
    assert queued == [], 'queued inside the transaction'


def test_the_real_type_decides_not_the_filename(author, subscribed, queued):
    """A video named .jpg is a video; a text file named .mp4 is refused."""
    as_jpg = create(author, upload('looks-like.jpg', MP4_HEADER, 'image/jpeg'))
    assert as_jpg.status_code == 201
    assert as_jpg.data['media_type'] == 'video'

    fake = create(author, upload('clip.mp4', b'just some text, not a video at all', 'video/mp4'))
    assert fake.status_code == 415
    assert fake.data['code'] == 'unsupported_file'


@pytest.mark.parametrize(
    ('name', 'content', 'kind'),
    [
        ('a.png', image_bytes('PNG'), 'image'),
        ('a.webp', image_bytes('WEBP'), 'image'),
        ('a.webm', WEBM_HEADER, 'video'),
        ('a.mov', b'\x00\x00\x00\x14ftypqt  ' + b'\x00' * 64, 'video'),
    ],
)
def test_supported_formats_are_accepted(author, subscribed, queued, name, content, kind):
    response = create(author, upload(name, content))
    assert response.status_code == 201, response.data
    assert response.data['media_type'] == kind


@pytest.mark.parametrize(
    ('content', 'code', 'status'),
    [
        (b'', 'empty_file', 400),
        (HEIC_HEADER, 'unsupported_image_format', 415),
        (b'%PDF-1.7 not media', 'unsupported_file', 415),
    ],
)
def test_bad_uploads_are_refused_with_a_code(author, queued, content, code, status):
    response = create(author, upload('x.bin', content))
    assert response.status_code == status, response.data
    assert response.data['code'] == code
    assert not Reel.objects.exists()


def test_the_size_limit_is_enforced(author, queued, settings):
    settings.MEDIA_MAX_UPLOAD_BYTES = 100
    response = create(author, upload('big.jpg', jpeg_bytes(200, 200, noise=True)))
    assert response.status_code == 413
    assert response.data['code'] == 'file_too_large'


def test_a_photo_with_too_many_pixels_is_refused(author, queued, settings):
    settings.MEDIA_MAX_IMAGE_PIXELS = 1000
    response = create(author, upload('huge.jpg', jpeg_bytes(100, 100)))
    assert response.status_code == 400
    assert response.data['code'] == 'image_too_large'


def test_a_missing_file_is_refused(author, queued):
    from api.views.core import create_post

    request = factory.post('/posts/create/', {'caption': 'no file'})
    force_authenticate(request, user=author)
    response = create_post(request)
    assert response.status_code == 400
    assert response.data['code'] == 'file_required'


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


@pytest.fixture
def dance():
    return Category.objects.create(name='Dance', slug='dance')


def test_the_chosen_category_is_saved_and_returned(author, queued, dance):
    response = create(author, upload('p.jpg', jpeg_bytes()), category=str(dance.id))

    assert response.status_code == 201
    assert response.data['category'] == dance.id
    assert response.data['category_name'] == 'Dance'
    assert Reel.objects.get(pk=response.data['id']).category == dance


def test_a_slug_works_for_older_clients(author, queued, dance):
    response = create(author, upload('p.jpg', jpeg_bytes()), category='dance')
    assert response.data['category'] == dance.id


@pytest.mark.parametrize('value', [None, '', 'null', 'undefined'])
def test_no_category_is_allowed(author, queued, value):
    data = {} if value is None else {'category': value}
    response = create(author, upload('p.jpg', jpeg_bytes()), **data)
    assert response.status_code == 201
    assert response.data['category'] is None


@pytest.mark.parametrize('value', ['424242', 'no-such-category'])
def test_an_unknown_category_is_refused_before_anything_is_stored(
    author, queued, value, media_root
):
    response = create(author, upload('p.jpg', jpeg_bytes()), category=value)

    assert response.status_code == 400
    assert response.data['code'] == 'invalid_category'
    assert not Reel.objects.exists()
    assert not os.path.exists(os.path.join(media_root, 'source'))


def test_an_inactive_category_is_refused(author, queued):
    retired = Category.objects.create(name='Old', slug='old', is_active=False)
    response = create(author, upload('p.jpg', jpeg_bytes()), category=str(retired.id))
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Retries: one submission, one post, one charge
# ---------------------------------------------------------------------------


@pytest.fixture
def paid_posts(author):
    from api.models.contest import UserCoinBalance
    from api.models.wallet import WalletConfig

    config = WalletConfig.get_config()
    config.cost_post_create_non_campaign = 5
    config.save()
    balance, _ = UserCoinBalance.objects.get_or_create(user=author)
    balance.add_coins(20, 'reward')
    return balance


def coins(user):
    from api.models.contest import UserCoinBalance

    return UserCoinBalance.objects.get(user=user).balance


def test_a_retried_submission_returns_the_same_post_and_charges_once(author, queued, paid_posts):
    before = coins(author)
    headers = {'HTTP_IDEMPOTENCY_KEY': 'upload-7f3a9c21'}
    first = create(author, upload('p.jpg', jpeg_bytes()), headers=headers)
    second = create(author, upload('p.jpg', jpeg_bytes()), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.data['id'] == first.data['id']
    assert Reel.objects.filter(user=author).count() == 1
    assert coins(author) == before - 5, 'charged twice'


def test_the_id_may_come_as_a_form_field(author, queued):
    first = create(author, upload('p.jpg', jpeg_bytes()), client_upload_id='form-field-id-1')
    second = create(author, upload('p.jpg', jpeg_bytes()), client_upload_id='form-field-id-1')
    assert second.data['id'] == first.data['id']


def test_different_submissions_make_different_posts(author, queued):
    a = create(author, upload('p.jpg', jpeg_bytes()), client_upload_id='submission-aaaa')
    b = create(author, upload('p.jpg', jpeg_bytes()), client_upload_id='submission-bbbb')
    assert a.data['id'] != b.data['id']


def test_the_same_id_from_another_user_is_their_own(author, stranger, queued):
    a = create(author, upload('p.jpg', jpeg_bytes()), client_upload_id='shared-id-0001')
    b = create(stranger, upload('p.jpg', jpeg_bytes()), client_upload_id='shared-id-0001')
    assert a.data['id'] != b.data['id']


def test_a_malformed_id_is_refused(author, queued):
    response = create(author, upload('p.jpg', jpeg_bytes()), client_upload_id='bad id!')
    assert response.status_code == 400
    assert response.data['code'] == 'invalid_idempotency_key'


def test_not_enough_coins_stores_nothing(author, queued, paid_posts, media_root):
    from api.models.wallet import WalletConfig

    config = WalletConfig.get_config()
    config.cost_post_create_non_campaign = 500
    config.save()

    response = create(author, upload('p.jpg', jpeg_bytes()))

    assert response.status_code == 400
    assert not Reel.objects.exists()
    leftovers = [
        f for _root, _d, files in os.walk(os.path.join(media_root, 'source')) for f in files
    ]
    assert leftovers == [], 'the unused original was kept'


# ---------------------------------------------------------------------------
# Errors are safe
# ---------------------------------------------------------------------------


def test_an_internal_failure_returns_no_traceback(author, queued, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError('SECRET-internal-detail /srv/app/db.py line 42')

    monkeypatch.setattr(Reel.objects, 'create', explode)
    response = create(author, upload('p.jpg', jpeg_bytes()))

    assert response.status_code == 500
    assert response.data == {
        'error': 'We could not create your post. Please try again.',
        'code': 'post_failed',
    }
    assert 'SECRET' not in str(response.data)


def test_a_missing_post_is_a_404_not_a_500(author):
    assert retrieve(author, 987654).status_code == 404


# ---------------------------------------------------------------------------
# Every upload endpoint uses the pipeline
# ---------------------------------------------------------------------------


def test_post_reels_is_the_same_path(author, queued, dance, django_capture_on_commit_callbacks):
    from api.views.core import ReelViewSet

    request = factory.post(
        '/reels/',
        {'media': upload('p.jpg', jpeg_bytes()), 'category': dance.id, 'overlay_text': '[]'},
    )
    force_authenticate(request, user=author)
    with django_capture_on_commit_callbacks(execute=True):
        response = ReelViewSet.as_view({'post': 'create'})(request)

    assert response.status_code == 201, response.data
    assert response.data['processing_status'] == 'PROCESSING'
    assert response.data['category'] == dance.id
    assert len(queued) == 1


def test_campaign_posts_are_processed_too(author, queued, django_capture_on_commit_callbacks):
    from api.models.campaign import Campaign
    from api.views.campaign_user import create_campaign_post

    now = timezone.now()
    campaign = Campaign.objects.create(
        title='Spring',
        description='d',
        prize_title='Prize',
        prize_description='pd',
        campaign_type='daily',
        start_date=now - timedelta(days=1),
        entry_deadline=now + timedelta(days=5),
        status='active',
    )

    def submit():
        request = factory.post(
            '/campaigns/posts/create/',
            {
                'campaign_id': campaign.id,
                'image': upload('p.jpg', jpeg_bytes()),
                'client_upload_id': 'entry-0001',
            },
        )
        force_authenticate(request, user=author)
        with django_capture_on_commit_callbacks(execute=True):
            return create_campaign_post(request)

    response = submit()
    assert response.status_code == 201, response.data
    assert response.data['processing_status'] == 'PROCESSING'
    reel = Reel.objects.get(pk=response.data['reel_id'])
    assert reel.processing_status == MediaStatus.PROCESSING
    assert reel.original_image.startswith('source/images/')
    assert len(queued) == 1

    retried = submit()
    assert retried.status_code == 200
    assert retried.data['reel_id'] == reel.pk
    assert retried.data['post_score_id'] == response.data['post_score_id']
    assert Reel.objects.filter(user=author).count() == 1
    assert len(queued) == 1


@pytest.fixture
def campaign():
    from api.models.campaign import Campaign

    now = timezone.now()
    return Campaign.objects.create(
        title='Spring',
        description='d',
        prize_title='Prize',
        prize_description='pd',
        campaign_type='daily',
        start_date=now - timedelta(days=1),
        entry_deadline=now + timedelta(days=5),
        status='active',
    )


OBS = 'https://obs.example/flipstar'


def processed_video(user, **extra):
    """A campaign video as the worker leaves it."""
    n = Reel.objects.count() + 1
    base = f'{OBS}/processed/videos/{n}/v1'
    return Reel.objects.create(
        user=user,
        is_campaign_post=True,
        media=f'{base}/720p.mp4',
        media_360=f'{base}/360p.mp4',
        media_480=f'{base}/480p.mp4',
        thumbnail=f'{OBS}/processed/thumbnails/{n}/v1/thumb.jpg',
        original_media=f'source/videos/{user.pk}/orig{n}.mp4',
        processed_at=timezone.now(),
        **extra,
    )


def unprocessed_video(user, **extra):
    return Reel.objects.create(
        user=user,
        is_campaign_post=True,
        media=f'source/videos/{user.pk}/pending.mp4',
        original_media=f'source/videos/{user.pk}/pending.mp4',
        processing_status=MediaStatus.PROCESSING,
        processed=False,
        **extra,
    )


def encrypted_get(view, viewer, path, keys, **kwargs):
    """Call an @encrypted_endpoint view. response.data is the plain payload:
    the seal is applied when the response renders."""
    _server_public, client_public, _client_private = keys
    request = factory.get(path, HTTP_X_CLIENT_PUBLIC_KEY=client_public)
    if viewer is not None:
        force_authenticate(request, user=viewer)
    return view(request, **kwargs)


def test_the_campaign_feed_offers_renditions_never_an_original(
    author, stranger, campaign, encrypted_client_keys
):
    """The web campaign feed picks a rung by connection; it needs the rungs."""
    import json

    from api.models.campaign_extended import PostScore
    from api.views.campaign_user import get_campaign_feed

    ready = processed_video(author, campaign=campaign)
    pending = unprocessed_video(stranger, campaign=campaign)
    for reel in (ready, pending):
        PostScore.objects.create(
            reel=reel, campaign=campaign, user=reel.user, moderation_status='approved'
        )

    response = encrypted_get(
        get_campaign_feed,
        stranger,
        f'/campaigns/{campaign.id}/feed/',
        encrypted_client_keys,
        campaign_id=campaign.id,
    )

    assert response.status_code == 200, response.data
    posts = response.data['posts']
    assert [p['reel']['id'] for p in posts] == [ready.pk], 'an unprocessed post reached the feed'
    reel = posts[0]['reel']
    assert reel['media'] == ready.media
    assert reel['media_variants'] == {'360': ready.media_360, '480': ready.media_480}
    assert reel['thumbnail'].endswith('/thumb.jpg')
    assert reel['processing_status'] == 'READY' and reel['media_type'] == 'video'
    assert 'source/' not in json.dumps(response.data, default=str)


def test_campaign_entries_offer_renditions_and_hide_unfinished_ones(
    author, stranger, campaign, encrypted_client_keys
):
    import json

    from api.models.campaign import CampaignEntry
    from api.views.campaign import user_campaign_detail

    ready = processed_video(author, campaign=campaign)
    pending = unprocessed_video(stranger, campaign=campaign)
    CampaignEntry.objects.create(campaign=campaign, user=author, reel=ready)
    CampaignEntry.objects.create(campaign=campaign, user=stranger, reel=pending)

    def entries(viewer):
        response = encrypted_get(
            user_campaign_detail,
            viewer,
            f'/campaigns/{campaign.id}/',
            encrypted_client_keys,
            campaign_id=campaign.id,
        )
        assert response.status_code == 200, response.data
        assert 'source/' not in json.dumps(response.data, default=str), 'an original was handed out'
        return {e['reel']['id']: e['reel'] for e in response.data['entries']}

    assert set(entries(author)) == {ready.pk}, "someone else's unprocessed entry was shown"
    assert set(entries(None)) == {ready.pk}
    own = entries(stranger)
    assert own[pending.pk]['processing_status'] == 'PROCESSING', 'the author lost their entry'
    assert own[pending.pk]['media'] is None
    assert own[ready.pk]['media_variants'] == {'360': ready.media_360, '480': ready.media_480}


def test_hand_built_urls_never_hand_out_an_original(author):
    from api.services.media_pipeline import served_url

    assert (
        served_url(f'{OBS}/processed/videos/1/v1/720p.mp4')
        == f'{OBS}/processed/videos/1/v1/720p.mp4'
    )
    assert served_url('source/videos/1/a.mp4') is None
    assert served_url(None) is None and served_url('') is None
    legacy = Reel(user=author, media='reels/old.mp4')
    assert served_url(legacy.media).endswith('/reels/old.mp4')
    pending = Reel(user=author, media='source/videos/1/a.mp4')
    assert served_url(pending.media) is None


def test_the_backfill_only_takes_posts_the_pipeline_has_not_finished(author, monkeypatch):
    """generate_missing_media re-encodes older posts that went out as their
    raw upload. It must not keep re-queueing ones already done."""
    from django.core.management import call_command

    legacy_video = Reel.objects.create(user=author, media=f'{OBS}/media/reels/raw-upload.mp4')
    small = Reel.objects.create(  # processed; a 360p source has no 480p rung
        user=author,
        media=f'{OBS}/processed/videos/9/v1/360p.mp4',
        media_360=f'{OBS}/processed/videos/9/v1/360p.mp4',
        thumbnail=f'{OBS}/processed/thumbnails/9/v1/thumb.jpg',
        processed_at=timezone.now(),
    )
    unprocessed_video(author)
    Reel.objects.create(
        user=author, media='source/videos/1/b.mp4', processing_status=MediaStatus.FAILED
    )
    old_photo = Reel.objects.create(  # an older pipeline's JPEGs, no WebP
        user=author,
        image=f'{OBS}/media/reels/p.jpg',
        image_small=f'{OBS}/media/reels/p_360.jpg',
        image_medium=f'{OBS}/media/reels/p_720.jpg',
        thumbnail=f'{OBS}/media/thumbnails/p.jpg',
    )

    sent = []
    monkeypatch.setattr(media_tasks.process_reel_media, 'delay', lambda pk: sent.append(pk))
    call_command('generate_missing_media', '--commit', '--sleep', '0', stdout=io.StringIO())
    assert sent == [legacy_video.pk]
    assert small.pk not in sent

    sent.clear()
    call_command(
        'generate_missing_media', '--commit', '--sleep', '0', '--only', 'webp', stdout=io.StringIO()
    )
    assert sent == [old_photo.pk]


# ---------------------------------------------------------------------------
# Object storage as a deployment configures it
# ---------------------------------------------------------------------------
#
# Staging runs with S3_DEFAULT_ACL empty: objects are private and every media
# URL is signed. There the worker sent a public-read ACL anyway (a fallback),
# OBS refused every processed file, and each web post ended FAILED.


class FakeS3:
    def __init__(self):
        self.uploads = []

    def upload_file(self, local_path, bucket, key, ExtraArgs=None):
        self.uploads.append((bucket, key, dict(ExtraArgs or {})))


@pytest.fixture
def obs(settings, monkeypatch):
    import boto3

    settings.S3_BUCKET_NAME = 'flipstar-media'
    settings.S3_ENDPOINT_URL = 'https://obs.example'
    settings.S3_REGION_NAME = 'et-global-3'
    settings.S3_ACCESS_KEY_ID = 'key'
    settings.S3_SECRET_ACCESS_KEY = 'secret'
    client = FakeS3()
    monkeypatch.setattr(boto3, 'client', lambda *a, **k: client)
    return client


def test_processed_files_carry_no_acl_where_none_is_configured(obs, settings, tmp_path):
    if hasattr(settings, 'AWS_DEFAULT_ACL'):
        del settings.AWS_DEFAULT_ACL
    local = tmp_path / 'full.jpg'
    local.write_bytes(b'jpeg')

    url = media_tasks._upload_to_s3(str(local), 'processed/images/1/v1/full.jpg')

    assert url == 'https://obs.example/flipstar-media/processed/images/1/v1/full.jpg'
    _bucket, _key, extra = obs.uploads[-1]
    assert 'ACL' not in extra, 'sent an ACL the deployment does not use'
    assert extra['ContentType'] == 'image/jpeg'
    assert 'immutable' in extra['CacheControl']


def test_processed_files_carry_the_configured_acl(obs, settings, tmp_path):
    settings.AWS_DEFAULT_ACL = 'public-read'
    local = tmp_path / '360p.mp4'
    local.write_bytes(b'mp4')
    media_tasks._upload_to_s3(str(local), 'processed/videos/1/v1/360p.mp4')
    assert obs.uploads[-1][2]['ACL'] == 'public-read'
    assert obs.uploads[-1][2]['ContentType'] == 'video/mp4'


def test_originals_carry_no_acl_where_none_is_configured(settings, monkeypatch):
    from api.services import media_pipeline
    from infrastructure.storage.config import S3_STORAGE

    settings.DEFAULT_FILE_STORAGE = S3_STORAGE
    settings.AWS_STORAGE_BUCKET_NAME = 'flipstar-media'
    if hasattr(settings, 'AWS_DEFAULT_ACL'):
        del settings.AWS_DEFAULT_ACL
    monkeypatch.setattr(media_pipeline, '_source_storage', None)
    assert media_pipeline.source_storage().default_acl is None

    settings.AWS_DEFAULT_ACL = 'public-read'
    monkeypatch.setattr(media_pipeline, '_source_storage', None)
    assert media_pipeline.source_storage().default_acl == 'private', 'an original went public'


def test_media_in_a_private_bucket_is_served_signed(author, stranger, settings, monkeypatch):
    from django.core.files.storage import default_storage

    from api.services.media_pipeline import servable_url

    settings.S3_BUCKET_NAME = 'flipstar-media'
    settings.S3_ENDPOINT_URL = 'https://obs.example'
    settings.AWS_QUERYSTRING_AUTH = True
    signed = []

    def sign(key):
        signed.append(key)
        return f'https://obs.example/flipstar-media/{key}?X-Amz-Signature=abc'

    monkeypatch.setattr(default_storage, 'url', sign)
    base = 'https://obs.example/flipstar-media/processed/videos/7/v1'
    reel = Reel.objects.create(user=author, media=f'{base}/720p.mp4', media_360=f'{base}/360p.mp4')

    row = list_reels(stranger)[reel.pk]
    assert row['media'] == f'{base}/720p.mp4?X-Amz-Signature=abc'
    assert row['media_variants']['360'] == f'{base}/360p.mp4?X-Amz-Signature=abc'
    assert 'processed/videos/7/v1/720p.mp4' in signed

    settings.AWS_QUERYSTRING_AUTH = False  # public objects: as stored
    assert servable_url(f'{base}/720p.mp4') == f'{base}/720p.mp4'
    elsewhere = 'https://res.cloudinary.com/demo/video/upload/clip.mp4'
    assert servable_url(elsewhere) == elsewhere
    assert servable_url('https://obs.example/flipstar-media/source/videos/1/a.mp4') is None


def test_output_storage_refusing_the_files_fails_with_its_own_code(
    image_post, settings, monkeypatch
):
    from celery.exceptions import Retry

    reel = image_post(jpeg_bytes(800, 600))
    settings.S3_BUCKET_NAME = 'flipstar-media'
    monkeypatch.setattr(media_tasks, '_upload_to_s3', lambda path, key: None)  # OBS refused

    for number in range(media_tasks.process_reel_media.max_retries):
        with pytest.raises(Retry):
            attempt(reel, number)
    assert attempt(reel, media_tasks.process_reel_media.max_retries).get() == (
        f'Reel {reel.pk} failed after retries'
    )
    reel.refresh_from_db()
    assert reel.processing_status == MediaStatus.FAILED
    assert reel.processing_error == 'storage_write_failed'


def test_the_s3_client_is_not_logged_at_debug():
    """At DEBUG it logs every URL signature -- ten lines each, the signature
    included -- which is what flooded the staging logs."""
    from common.constants.logging import build_logging_config

    loggers = build_logging_config(level='DEBUG')['loggers']
    for name in ('botocore', 'boto3', 's3transfer', 'urllib3'):
        assert loggers[name]['level'] == 'WARNING', name
    assert loggers['api']['level'] == 'DEBUG', 'the app itself should still follow LOG_LEVEL'


# ---------------------------------------------------------------------------
# Replacing a post's media, and deleting a post
# ---------------------------------------------------------------------------


def edit(user, pk, **data):
    from api.views.core import ReelViewSet

    request = factory.patch(f'/reels/{pk}/', data, format='multipart')
    force_authenticate(request, user=user)
    return ReelViewSet.as_view({'patch': 'partial_update'})(request, pk=pk)


def remove(user, pk):
    from api.views.core import ReelViewSet

    request = factory.delete(f'/reels/{pk}/')
    force_authenticate(request, user=user)
    return ReelViewSet.as_view({'delete': 'destroy'})(request, pk=pk)


@pytest.fixture
def ready_image_post(image_post):
    reel = image_post(jpeg_bytes(800, 600))
    assert process(reel) == f'Reel {reel.pk} processed OK'
    reel.refresh_from_db()
    return reel


def test_replacing_media_goes_through_the_pipeline(
    ready_image_post,
    author,
    stranger,
    queued,
    media_root,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    reel = ready_image_post
    old_source, old_full = reel.original_image, str(reel.image)
    cleanup = []
    monkeypatch.setattr(media_tasks.delete_post_media, 'delay', lambda *a: cleanup.append(a))

    with django_capture_on_commit_callbacks(execute=True):
        response = edit(
            author, reel.pk, caption='new', file=upload('n.png', image_bytes('PNG', 500, 500))
        )

    assert response.status_code == 200, response.data
    assert response.data['processing_status'] == 'PROCESSING'
    assert response.data['caption'] == 'new'
    assert response.data['image'] is None, 'the new original must not be served'
    assert response.data['image_variants'] is None, 'the old media is still advertised'
    assert response.data['image_webp_variants'] is None
    assert response.data['thumbnail'] is None
    reel.refresh_from_db()
    assert (
        reel.original_image.startswith(f'source/images/{author.pk}/')
        and reel.original_image != old_source
    )
    assert reel.media_version == 2, 'a version is reserved so an older run cannot collide'
    assert queued[-1] == ((reel.pk,), {})
    assert cleanup == [(reel.pk, [old_source], [])], 'the replaced original was kept'
    assert reel.pk not in list_reels(stranger)
    old_output = os.path.join(media_root, f'processed/images/{reel.pk}/v1/full.jpg')
    assert os.path.exists(old_output), 'old files removed before the new ones exist'

    # The new media is processed into a new version; only then do the old
    # files go.
    assert process(reel) == f'Reel {reel.pk} processed OK'
    reel.refresh_from_db()
    assert str(reel.image).endswith('/v3/full.jpg') and str(reel.image) != old_full
    assert not os.path.exists(old_output), 'the replaced media was left behind'
    assert os.path.exists(os.path.join(media_root, str(reel.image)))


def test_a_retried_media_edit_is_applied_once(
    ready_image_post, author, queued, django_capture_on_commit_callbacks
):
    """A retry after the answer to a replacement was lost: the same edit, not
    a 409 telling the person it failed, and not a second replacement."""
    with django_capture_on_commit_callbacks(execute=True):
        first = edit(
            author,
            ready_image_post.pk,
            file=upload('n.jpg', jpeg_bytes()),
            client_upload_id='edit-0001',
        )
    source = Reel.objects.get(pk=ready_image_post.pk).original_image
    with django_capture_on_commit_callbacks(execute=True):
        again = edit(
            author,
            ready_image_post.pk,
            file=upload('n.jpg', jpeg_bytes()),
            client_upload_id='edit-0001',
        )

    assert first.status_code == 200 and again.status_code == 200
    assert again.data['processing_status'] == 'PROCESSING'
    assert Reel.objects.get(pk=ready_image_post.pk).original_image == source, 'replaced twice'
    assert len(queued) == 1

    other = edit(
        author,
        ready_image_post.pk,
        file=upload('m.jpg', jpeg_bytes()),
        client_upload_id='edit-0002',
    )
    assert other.status_code == 409, 'a different edit while processing'


def test_media_cannot_be_replaced_while_it_is_processing(image_post, author, queued):
    reel = image_post(jpeg_bytes())
    response = edit(author, reel.pk, file=upload('n.jpg', jpeg_bytes()))
    assert response.status_code == 409
    assert response.data['code'] == 'post_processing'


def test_replacing_with_a_video_is_for_subscribers(ready_image_post, author, queued, monkeypatch):
    import api.views.core as core

    monkeypatch.setattr(core, 'has_active_subscription', lambda user: False)
    monkeypatch.setattr(
        'api.services.subscription_renewal.check_and_renew_subscription',
        lambda user: type('R', (), {'has_subscription': False, 'state': 'none'})(),
    )
    response = edit(author, ready_image_post.pk, file=upload('v.mp4', MP4_HEADER))
    assert response.status_code == 403
    assert response.data['code'] == 'SUBSCRIPTION_REQUIRED'
    ready_image_post.refresh_from_db()
    assert ready_image_post.processing_status == MediaStatus.READY


def test_a_bad_replacement_file_is_refused(ready_image_post, author, queued):
    response = edit(
        author, ready_image_post.pk, file=upload('x.mp4', b'not a video at all, just text')
    )
    assert response.status_code == 415
    assert response.data['code'] == 'unsupported_file'


def test_a_caption_edit_leaves_the_media_alone(ready_image_post, author, queued):
    response = edit(author, ready_image_post.pk, caption='just words')
    assert response.status_code == 200
    assert response.data['processing_status'] == 'READY'
    assert queued == []


def test_someone_else_cannot_replace_the_media(ready_image_post, stranger, queued):
    assert (
        edit(stranger, ready_image_post.pk, file=upload('n.jpg', jpeg_bytes())).status_code == 403
    )


def test_deleting_a_post_removes_its_original_and_processed_media(
    ready_image_post, author, media_root, django_capture_on_commit_callbacks
):
    reel = ready_image_post
    source, full = reel.original_image, os.path.join(media_root, str(reel.image))
    assert stored(source) and os.path.exists(full)

    with django_capture_on_commit_callbacks(execute=True):
        assert remove(author, reel.pk).status_code == 204

    assert not Reel.objects.filter(pk=reel.pk).exists()
    assert not stored(source), 'the private original was left behind'
    assert not os.path.exists(
        os.path.join(media_root, f'processed/images/{reel.pk}')
    ), 'outputs left behind'


def test_a_failed_delete_returns_no_internals(ready_image_post, author, monkeypatch):
    from api.views.core import ReelViewSet

    def explode(*args, **kwargs):
        raise RuntimeError('SECRET relation "api_reel" /srv/app')

    monkeypatch.setattr(ReelViewSet, 'get_object', explode)
    response = remove(author, ready_image_post.pk)
    assert response.status_code == 500
    assert response.data == {
        'error': 'We could not delete this post. Please try again.',
        'code': 'delete_failed',
    }


def test_a_run_that_lost_its_hold_does_not_write(image_post, monkeypatch):
    reel = image_post(jpeg_bytes(800, 600))
    real = media_tasks._run_image

    def replaced_meanwhile(*args, **kwargs):
        result = real(*args, **kwargs)
        Reel.objects.filter(pk=reel.pk).update(processing_task_id='a-newer-task')
        return result

    monkeypatch.setattr(media_tasks, '_run_image', replaced_meanwhile)
    assert process(reel) == f'Reel {reel.pk}: superseded'
    reel.refresh_from_db()
    assert reel.processing_status == MediaStatus.PROCESSING
    assert reel.processing_task_id == 'a-newer-task'
    assert reel.media_version == 0


def test_an_older_post_with_a_still_in_media_is_an_image(author, stranger):
    legacy = Reel.objects.create(user=author, media='https://obs.example/media/reels/old.jpg')
    assert list_reels(stranger)[legacy.pk]['media_type'] == 'image'


# ---------------------------------------------------------------------------
# Only READY media reaches feeds
# ---------------------------------------------------------------------------


def test_a_processing_post_is_kept_out_of_feeds_but_shown_to_its_author(author, stranger, queued):
    pk = create(author, upload('p.jpg', jpeg_bytes())).data['id']

    assert pk not in list_reels(stranger), "shown in a stranger's feed"
    assert pk not in list_reels(None), 'shown to an anonymous visitor'
    assert pk not in list_reels(author), "shown in the author's own home feed"
    own = list_reels(author, user=author.pk)
    assert own[pk]['processing_status'] == 'PROCESSING', "missing from the author's profile"
    assert pk not in list_reels(stranger, user=author.pk), "shown on the author's profile to others"

    assert retrieve(author, pk).status_code == 200
    assert retrieve(stranger, pk).status_code == 404


def test_older_posts_are_unaffected(author, stranger):
    """Every existing row is READY by default and served as it always was."""
    legacy = Reel.objects.create(user=author, media='https://obs.example/media/reels/old.mp4')
    row = list_reels(stranger)[legacy.pk]
    assert row['processing_status'] == 'READY'
    assert row['media'] == 'https://obs.example/media/reels/old.mp4'


# ---------------------------------------------------------------------------
# The worker: images (Pillow only)
# ---------------------------------------------------------------------------


@pytest.fixture
def image_post(author, queued):
    def make(content, name='p.jpg'):
        pk = create(author, upload(name, content)).data['id']
        return Reel.objects.get(pk=pk)

    return make


def test_an_image_is_processed_into_jpeg_webp_variants_and_a_thumbnail(
    image_post, media_root, stranger
):
    reel = image_post(photo_bytes(1600, 1200))

    assert process(reel) == f'Reel {reel.pk} processed OK'
    reel.refresh_from_db()
    assert reel.processing_status == MediaStatus.READY
    assert reel.processed and not reel.processing_failed
    assert reel.media_version == 1
    assert reel.processed_at is not None

    def at(key):
        return os.path.join(media_root, str(key))

    with Image.open(at(reel.image)) as full:
        assert full.format == 'JPEG' and max(full.size) == 1080
        assert full.info.get('progressive') or full.info.get('progression')
    with open(at(reel.image_webp), 'rb') as fh:
        head = fh.read(12)
    assert head[:4] == b'RIFF' and head[8:12] == b'WEBP', 'not actually WebP'
    with Image.open(at(reel.image_webp)) as webp:
        assert webp.size == (1080, 810)
    for field, width in (('image_small', 360), ('image_medium', 720)):
        with Image.open(at(getattr(reel, field))) as jpg:
            assert jpg.format == 'JPEG' and jpg.width == width
        with Image.open(at(getattr(reel, f'{field}_webp'))) as webp:
            assert webp.format == 'WEBP' and webp.width == width
    with Image.open(at(reel.thumbnail)) as thumb:
        assert thumb.size == (320, 720)

    assert os.path.getsize(at(reel.image_webp)) < os.path.getsize(
        at(reel.image)
    ), 'WebP is not smaller'
    assert reel.processed_size < reel.source_size

    row = list_reels(stranger)[reel.pk]
    assert row['processing_status'] == 'READY'
    assert row['image'].endswith(f'processed/images/{reel.pk}/v1/full.jpg')
    assert set(row['image_variants']) == {'360', '720'}
    assert set(row['image_webp_variants']) == {'360', '720', 'full'}
    assert row['thumbnail'].endswith(f'processed/thumbnails/{reel.pk}/v1/thumb.jpg')


def test_orientation_is_corrected(image_post, media_root):
    """A phone photo stored sideways with the fix only in EXIF comes out upright."""
    reel = image_post(jpeg_bytes(400, 200, exif_orientation=6))
    process(reel)
    reel.refresh_from_db()
    with Image.open(os.path.join(media_root, str(reel.image))) as img:
        assert img.size == (200, 400)
        assert not img.getexif().get(0x0112), 'EXIF carried into the served copy'


def test_a_small_image_is_not_upscaled(image_post, media_root):
    reel = image_post(jpeg_bytes(300, 200))
    process(reel)
    reel.refresh_from_db()
    with Image.open(os.path.join(media_root, str(reel.image))) as img:
        assert img.size == (300, 200)
    assert reel.image_small == '' and reel.image_medium == '', 'variants wider than the source'


@pytest.mark.parametrize(('fmt', 'mode'), [('PNG', 'RGB'), ('PNG', 'RGBA'), ('WEBP', 'RGB')])
def test_png_and_webp_sources_work(image_post, media_root, fmt, mode):
    reel = image_post(image_bytes(fmt, 800, 800, mode=mode), name=f'p.{fmt.lower()}')
    process(reel)
    reel.refresh_from_db()
    assert reel.processing_status == MediaStatus.READY
    with Image.open(os.path.join(media_root, str(reel.image))) as img:
        assert img.format == 'JPEG'
    with Image.open(os.path.join(media_root, reel.image_webp)) as img:
        assert img.format == 'WEBP'


def test_webp_is_only_kept_when_it_is_meaningfully_smaller(tmp_path):
    """A client told to prefer WebP must not end up downloading more -- or a
    second copy that saves next to nothing."""
    jpg, webp = tmp_path / 'a.jpg', tmp_path / 'a.webp'
    jpg.write_bytes(b'j' * 1000)

    for size, kept in (
        (470, True),
        (900, True),
        (901, False),
        (950, False),
        (1000, False),
        (1200, False),
    ):
        webp.write_bytes(b'w' * size)
        result = media_tasks._keep_webp(str(webp), str(jpg))
        assert (result == str(webp)) is kept, f'{size}-byte WebP next to a 1000-byte JPEG'
    assert media_tasks._keep_webp(None, str(jpg)) is None


def test_a_processed_post_is_not_processed_again(image_post):
    reel = image_post(jpeg_bytes(800, 600))
    process(reel)
    assert process(reel) == f'Reel {reel.pk}: already processed'
    reel.refresh_from_db()
    assert reel.media_version == 1


def test_a_post_held_by_another_task_is_left_alone(image_post):
    reel = image_post(jpeg_bytes(800, 600))
    Reel.objects.filter(pk=reel.pk).update(
        processing_task_id='someone-else', processing_started_at=timezone.now()
    )

    assert process(reel) == f'Reel {reel.pk}: held by another task'
    reel.refresh_from_db()
    assert reel.processing_status == MediaStatus.PROCESSING


def test_an_abandoned_hold_is_taken_over(image_post):
    reel = image_post(jpeg_bytes(800, 600))
    Reel.objects.filter(pk=reel.pk).update(
        processing_task_id='dead-worker', processing_started_at=timezone.now() - timedelta(hours=2)
    )
    assert process(reel) == f'Reel {reel.pk} processed OK'


def test_forced_reprocessing_writes_a_new_version_and_removes_the_old(image_post, media_root):
    reel = image_post(jpeg_bytes(800, 600))
    process(reel)
    old = os.path.join(media_root, f'processed/images/{reel.pk}/v1/full.jpg')
    assert os.path.exists(old)

    process(reel, force=True)
    reel.refresh_from_db()
    assert reel.media_version == 2
    assert str(reel.image).endswith('/v2/full.jpg')
    assert reel.processing_status == MediaStatus.READY
    assert not os.path.exists(old), 'the superseded version was kept'


def test_an_unreadable_image_is_refused_at_upload(author, queued):
    response = create(author, upload('p.jpg', b'\xff\xd8\xff' + b'garbage' * 50))
    assert response.status_code == 400
    assert response.data['code'] == 'unreadable_image'
    assert not Reel.objects.exists()


def test_an_unreadable_image_fails_at_once_with_a_code(author, stranger, media_root):
    """One that reached the worker anyway -- an older post, an older client."""
    key = f'source/images/{author.pk}/broken.jpg'
    os.makedirs(os.path.dirname(os.path.join(media_root, key)), exist_ok=True)
    with open(os.path.join(media_root, key), 'wb') as fh:
        fh.write(b'\xff\xd8\xff' + b'garbage' * 50)
    reel = Reel.objects.create(
        user=author,
        image=key,
        original_image=key,
        processing_status=MediaStatus.PROCESSING,
        processed=False,
    )

    assert process(reel) == f'Reel {reel.pk} rejected: invalid_media'
    reel.refresh_from_db()
    assert reel.processing_status == MediaStatus.FAILED
    assert reel.processing_error == 'invalid_media'
    assert reel.processing_failed and not reel.processed
    assert reel.pk not in list_reels(stranger)
    assert list_reels(reel.user, user=reel.user.pk)[reel.pk]['processing_error'] == 'invalid_media'


def test_transient_errors_retry_then_fail(image_post, monkeypatch):
    from celery.exceptions import Retry

    reel = image_post(jpeg_bytes(800, 600))
    attempts = []

    def flaky(*args, **kwargs):
        attempts.append(1)
        raise OSError('OBS timed out')

    monkeypatch.setattr(media_tasks, '_run_image', flaky)
    retries = media_tasks.process_reel_media.max_retries
    for number in range(retries):
        with pytest.raises(Retry):
            attempt(reel, number)
        reel.refresh_from_db()
        assert (
            reel.processing_status == MediaStatus.PROCESSING
        ), 'gave up before the retries ran out'
        assert reel.processing_task_id == 'task-1', 'the retry lost its hold on the post'

    assert attempt(reel, retries).get() == f'Reel {reel.pk} failed after retries'
    assert len(attempts) == retries + 1
    reel.refresh_from_db()
    assert reel.processing_status == MediaStatus.FAILED
    assert reel.processing_error == 'processing_failed'
    assert reel.processing_task_id == ''


def test_a_retry_resumes_after_a_transient_error(image_post, monkeypatch):
    from celery.exceptions import Retry

    reel = image_post(jpeg_bytes(800, 600))
    real = media_tasks._run_image
    calls = []

    def once_then_ok(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OSError('connection reset')
        return real(*args, **kwargs)

    monkeypatch.setattr(media_tasks, '_run_image', once_then_ok)
    with pytest.raises(Retry):
        attempt(reel, 0)
    assert attempt(reel, 1).get() == f'Reel {reel.pk} processed OK'
    reel.refresh_from_db()
    assert reel.processing_status == MediaStatus.READY
    assert reel.media_version == 1


def test_a_failed_post_is_reprocessed_on_request(image_post, monkeypatch):
    reel = image_post(jpeg_bytes(800, 600))
    Reel.objects.filter(pk=reel.pk).update(
        processing_status=MediaStatus.FAILED, processing_error='processing_failed'
    )

    assert 'failed; re-queue' in process(reel)
    assert process(reel, force=True) == f'Reel {reel.pk} processed OK'
    reel.refresh_from_db()
    assert reel.processing_status == MediaStatus.READY
    assert reel.processing_error == ''


def test_an_older_post_is_backfilled_and_stays_visible(author, stranger, media_root):
    """generate_missing_media queues posts published before the pipeline."""
    os.makedirs(os.path.join(media_root, 'reels'), exist_ok=True)
    with open(os.path.join(media_root, 'reels', 'legacy.jpg'), 'wb') as fh:
        fh.write(jpeg_bytes(1200, 900))
    legacy = Reel.objects.create(user=author, image='reels/legacy.jpg')

    assert process(legacy) == f'Reel {legacy.pk} processed OK'
    legacy.refresh_from_db()
    assert legacy.processing_status == MediaStatus.READY
    assert legacy.image_small and legacy.image_webp
    assert legacy.original_image == 'reels/legacy.jpg'


def test_a_failed_backfill_keeps_serving_the_old_media(author, stranger, monkeypatch):
    # Permanent: the older post's file cannot be found.
    legacy = Reel.objects.create(user=author, image='reels/missing.jpg')
    assert process(legacy) == f'Reel {legacy.pk} rejected: source_missing'
    legacy.refresh_from_db()
    assert legacy.processing_status == MediaStatus.READY, 'a working post was taken down'
    assert legacy.processing_failed, 'the failure was not recorded for the admin'
    assert legacy.pk in list_reels(stranger)

    # Transient, on the last retry.
    other = Reel.objects.create(user=author, image='reels/other.jpg')
    monkeypatch.setattr(media_tasks, '_run_image', lambda *a: (_ for _ in ()).throw(OSError('x')))
    attempt(other, media_tasks.process_reel_media.max_retries)
    other.refresh_from_db()
    assert other.processing_status == MediaStatus.READY, 'a working post was taken down'
    assert other.pk in list_reels(stranger)


# ---------------------------------------------------------------------------
# Re-drive and retention
# ---------------------------------------------------------------------------


def test_a_post_whose_task_never_arrived_is_requeued(image_post, monkeypatch):
    reel = image_post(jpeg_bytes())
    Reel.objects.filter(pk=reel.pk).update(created_at=timezone.now() - timedelta(minutes=30))
    sent = []
    monkeypatch.setattr(media_tasks.process_reel_media, 'delay', lambda pk: sent.append(pk))

    assert media_tasks.redrive_stuck_media() == 'Re-queued 1 post(s)'
    assert sent == [reel.pk]


def test_a_fresh_post_is_not_requeued(image_post, monkeypatch):
    image_post(jpeg_bytes())
    sent = []
    monkeypatch.setattr(media_tasks.process_reel_media, 'delay', lambda pk: sent.append(pk))
    media_tasks.redrive_stuck_media()
    assert sent == []


def test_originals_are_kept_by_default(image_post, settings):
    reel = image_post(jpeg_bytes(800, 600))
    process(reel)
    Reel.objects.filter(pk=reel.pk).update(processed_at=timezone.now() - timedelta(days=400))

    assert media_tasks.purge_processed_sources() == 'Retention disabled; originals are kept.'
    assert stored(Reel.objects.get(pk=reel.pk).original_image)


def test_originals_are_deleted_after_the_retention_period(image_post, settings):
    settings.MEDIA_SOURCE_RETENTION_DAYS = 7
    reel = image_post(jpeg_bytes(800, 600))
    process(reel)
    Reel.objects.filter(pk=reel.pk).update(processed_at=timezone.now() - timedelta(days=8))
    reel.refresh_from_db()

    assert media_tasks.purge_processed_sources() == 'Removed 1 original(s)'
    assert not stored(reel.original_image)
    reel.refresh_from_db()
    assert reel.source_deleted_at is not None
    assert reel.processing_status == MediaStatus.READY


def test_an_original_is_never_deleted_before_processing_succeeds(image_post, settings):
    settings.MEDIA_SOURCE_RETENTION_DAYS = 1
    reel = image_post(jpeg_bytes(800, 600))  # still PROCESSING
    Reel.objects.filter(pk=reel.pk).update(created_at=timezone.now() - timedelta(days=30))

    media_tasks.purge_processed_sources()
    assert stored(reel.original_image)


def test_an_original_is_kept_when_the_processed_file_is_missing(image_post, settings, media_root):
    settings.MEDIA_SOURCE_RETENTION_DAYS = 1
    reel = image_post(jpeg_bytes(800, 600))
    process(reel)
    reel.refresh_from_db()
    os.remove(os.path.join(media_root, str(reel.image)))
    Reel.objects.filter(pk=reel.pk).update(processed_at=timezone.now() - timedelta(days=5))

    assert media_tasks.purge_processed_sources() == 'Removed 0 original(s)'
    assert stored(reel.original_image)


# ---------------------------------------------------------------------------
# Long videos are charged by the worker, once
# ---------------------------------------------------------------------------


def test_the_long_video_surcharge_is_charged_once(author, paid_posts):
    from api.models.wallet import WalletConfig

    config = WalletConfig.get_config()
    config.cost_post_create_long_video_non_campaign = 7
    config.save()
    reel = Reel.objects.create(user=author, processing_status=MediaStatus.PROCESSING)
    before = coins(author)

    media_tasks._charge_long_video(reel, 75)
    reel.refresh_from_db()
    media_tasks._charge_long_video(reel, 75)

    assert coins(author) == before - 7
    assert reel.long_video_charged == 7


def test_a_short_video_is_not_surcharged(author, paid_posts):
    from api.models.wallet import WalletConfig

    config = WalletConfig.get_config()
    config.cost_post_create_long_video_non_campaign = 7
    config.save()
    reel = Reel.objects.create(user=author, processing_status=MediaStatus.PROCESSING)
    before = coins(author)

    media_tasks._charge_long_video(reel, 59.9)
    assert coins(author) == before


def test_an_unpaid_long_video_fails_instead_of_posting_free(author, paid_posts):
    from api.models.wallet import WalletConfig

    config = WalletConfig.get_config()
    config.cost_post_create_long_video_non_campaign = 5000
    config.save()
    reel = Reel.objects.create(user=author, processing_status=MediaStatus.PROCESSING)
    before = coins(author)

    with pytest.raises(media_tasks._Permanent) as exc:
        media_tasks._charge_long_video(reel, 75)
    assert exc.value.code == 'long_video_unpaid'
    reel.refresh_from_db()
    assert reel.long_video_charged == 0, 'recorded a charge that did not happen'
    assert coins(author) == before


# ---------------------------------------------------------------------------
# The worker: videos (real FFmpeg)
# ---------------------------------------------------------------------------


def make_video(
    path,
    width,
    height,
    seconds=2,
    audio=True,
    codec='libx264',
    rotate=None,
    location=True,
    pix_fmt='yuv444p',
    bitrate=None,
):
    """A synthetic clip: moving test pattern, optional tone and GPS tag."""
    cmd = ['ffmpeg', '-y', '-v', 'error']
    if rotate is not None:
        cmd += ['-display_rotation', str(rotate)]
    cmd += ['-f', 'lavfi', '-i', f'testsrc2=size={width}x{height}:rate=30:duration={seconds}']
    if audio:
        cmd += ['-f', 'lavfi', '-i', f'sine=frequency=440:duration={seconds}']
    if codec == 'libvpx':
        cmd += ['-c:v', 'libvpx', '-b:v', '1M']
        if audio:
            cmd += ['-c:a', 'libopus']
    else:
        cmd += ['-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', pix_fmt]
        if bitrate:
            cmd += ['-b:v', bitrate]
        if audio:
            cmd += ['-c:a', 'aac']
    if location:
        cmd += ['-metadata', 'location=+09.0300+038.7400/']
    cmd += [str(path)]
    subprocess.run(cmd, check=True)  # noqa: S603 - a fixed ffmpeg command line
    with open(path, 'rb') as fh:
        return fh.read()


def ffprobe(path):
    import ffmpeg

    return ffmpeg.probe(path)


@pytest.fixture
def video_post(author, subscribed, queued, tmp_path):
    def make(width, height, name='clip.mp4', **kwargs):
        content = make_video(tmp_path / name, width, height, **kwargs)
        pk = create(author, upload(name, content)).data['id']
        return Reel.objects.get(pk=pk)

    return make


def outputs(reel, media_root):
    """(rung-or-primary, path) for every rendition the post advertises."""
    paths = {'primary': os.path.join(media_root, str(reel.media))}
    for field in ('media_360', 'media_480'):
        value = getattr(reel, field)
        if value:
            paths[field] = os.path.join(media_root, value)
    return paths


@needs_ffmpeg
@pytest.mark.parametrize(
    ('width', 'height', 'audio', 'rungs'),
    [
        (1080, 1920, True, (360, 480, 720)),  # 9:16, 1080p phone video
        (1920, 1080, True, (360, 480, 720)),  # 16:9
        (720, 720, False, (360, 480, 720)),  # 1:1, no audio
        (720, 1280, True, (360, 480, 720)),  # 720p vertical
        (480, 854, True, (360, 480)),  # 480p source: no 720p rung
        (360, 640, True, (360,)),  # 360p source
    ],
)
def test_the_video_ladder(video_post, media_root, stranger, width, height, audio, rungs):
    reel = video_post(width, height, audio=audio)

    assert process(reel) == f'Reel {reel.pk} processed OK'
    reel.refresh_from_db()
    assert reel.processing_status == MediaStatus.READY
    assert 1.5 < reel.duration < 2.5

    source_ratio = width / height
    produced = set()
    for label, path in outputs(reel, media_root).items():
        info = ffprobe(path)
        v = next(s for s in info['streams'] if s['codec_type'] == 'video')
        a = [s for s in info['streams'] if s['codec_type'] == 'audio']
        w, h = int(v['width']), int(v['height'])
        short = min(w, h)
        produced.add(short)
        assert v['codec_name'] == 'h264', label
        assert v['pix_fmt'] == 'yuv420p', label
        assert v['profile'] == 'High', label
        assert short <= min(width, height), f'{label} upscaled: {w}x{h}'
        assert abs(w / h - source_ratio) < 0.02, f'{label} changed the aspect: {w}x{h}'
        assert w % 2 == 0 and h % 2 == 0
        if audio:
            assert a and a[0]['codec_name'] == 'aac', label
        else:
            assert not a, label
        assert 'location' not in (info['format'].get('tags') or {}), f'{label} kept GPS metadata'
        with open(path, 'rb') as fh:
            data = fh.read()
        assert data.index(b'moov') < data.index(b'mdat'), f'{label} is not faststart'
    assert produced == set(rungs), f'rungs {sorted(produced)}, expected {rungs}'

    with Image.open(os.path.join(media_root, str(reel.thumbnail))) as thumb:
        assert thumb.size == (320, 720)

    row = list_reels(stranger)[reel.pk]
    assert row['media'].endswith(f'processed/videos/{reel.pk}/v1/{max(rungs)}p.mp4')
    # Every low rung is advertised, so a client picking "360" on a slow
    # network always finds one. When that rung is the primary it is the same
    # object, not a second copy.
    variants = row['media_variants'] or {}
    assert set(variants) == {str(r) for r in rungs if r in (360, 480)}
    for rung, url in variants.items():
        if int(rung) == max(rungs):
            assert url == row['media']
        else:
            assert url.endswith(f'/v1/{rung}p.mp4')


@needs_ffmpeg
def test_a_rotated_phone_video_keeps_its_display_orientation(video_post, media_root):
    """Stored landscape with a 90-degree display rotation: shown portrait."""
    reel = video_post(1280, 720, rotate=90)
    process(reel)
    reel.refresh_from_db()
    v = next(
        s
        for s in ffprobe(os.path.join(media_root, str(reel.media)))['streams']
        if s['codec_type'] == 'video'
    )
    assert int(v['width']) < int(v['height']), 'rotation lost'
    assert min(int(v['width']), int(v['height'])) == 720


@needs_ffmpeg
def test_a_browser_webm_recording_becomes_mp4(video_post, media_root):
    reel = video_post(480, 640, name='rec.webm', codec='libvpx')
    process(reel)
    reel.refresh_from_db()
    info = ffprobe(os.path.join(media_root, str(reel.media)))
    assert info['format']['format_name'].startswith('mov,mp4')
    assert {s['codec_name'] for s in info['streams']} == {'h264', 'aac'}
    assert reel.duration and reel.duration > 1


@needs_ffmpeg
def test_a_tiny_video_still_plays(video_post, media_root):
    reel = video_post(240, 426)
    process(reel)
    reel.refresh_from_db()
    assert reel.processing_status == MediaStatus.READY
    v = next(
        s
        for s in ffprobe(os.path.join(media_root, str(reel.media)))['streams']
        if s['codec_type'] == 'video'
    )
    assert (int(v['width']), int(v['height'])) == (240, 426)


@needs_ffmpeg
def test_the_encode_is_smaller_than_a_heavy_source(video_post, media_root):
    reel = video_post(1080, 1920, seconds=3)
    process(reel)
    reel.refresh_from_db()
    assert reel.processed_size < reel.source_size


@needs_ffmpeg
def test_an_efficient_upload_is_not_made_bigger(video_post, media_root):
    """720p H.264 at a low bitrate: re-encoding it at 720p only adds bytes.
    The 720p rung is the upload's own streams re-wrapped -- still faststart,
    still without its metadata -- and the smaller rungs are still encoded."""
    reel = video_post(720, 1280, seconds=3, pix_fmt='yuv420p', bitrate='250k')
    assert process(reel) == f'Reel {reel.pk} processed OK'
    reel.refresh_from_db()

    primary = os.path.join(media_root, str(reel.media))
    assert os.path.getsize(primary) <= reel.source_size, 'the served 720p is bigger than the upload'
    info = ffprobe(primary)
    v = next(s for s in info['streams'] if s['codec_type'] == 'video')
    assert (int(v['width']), int(v['height'])) == (720, 1280)
    assert v['codec_name'] == 'h264' and v['pix_fmt'] == 'yuv420p'
    assert 'location' not in (info['format'].get('tags') or {}), 'kept GPS metadata'
    with open(primary, 'rb') as fh:
        data = fh.read()
    assert data.index(b'moov') < data.index(b'mdat'), 'not faststart'
    assert reel.media_360 and reel.media_480, 'the smaller rungs went missing'


@needs_ffmpeg
def test_a_video_over_the_limit_fails(video_post, settings):
    settings.MEDIA_MAX_VIDEO_SECONDS = 1
    reel = video_post(360, 640, seconds=3)
    assert process(reel) == f'Reel {reel.pk} rejected: video_too_long'
    reel.refresh_from_db()
    assert reel.processing_status == MediaStatus.FAILED
    assert reel.processing_error == 'video_too_long'


@needs_ffmpeg
def test_a_file_that_is_not_really_a_video_fails(author, subscribed, queued):
    pk = create(author, upload('x.mp4', MP4_HEADER)).data['id']
    reel = Reel.objects.get(pk=pk)
    assert process(reel) == f'Reel {reel.pk} rejected: invalid_media'
