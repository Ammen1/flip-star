"""
"Video unavailable": media that loaded, then did not.

What was wrong
--------------
Staging's bucket is private, so every media URL the API returns is presigned
and stops working an hour later (django-storages' default, never stated in
settings). The web app held those URLs for as long as a page stayed open and
replayed them from its feed caches; a card whose video failed once hid the
player for good; and nothing on the server heard about any of it. A post
that had been edited or re-processed since the client fetched it pointed at
files the worker had already removed.

What these pin
--------------
  refresh     POST /posts/media/ answers with media signed now, the same
              fields the feed carries, for posts the caller may see
  diagnosis   a reported failure is explained -- expired signature, media
              since replaced, missing or refused in storage, storage down,
              clocks apart, or nothing wrong on the server's side -- and
              logged as `media.unavailable` without the signature
  renditions  one storage says is missing is left out of the answer; a post
              whose files are gone is re-processed from its original, once
  safety      moderation and processing state decide visibility exactly as
              in the feed; an original under source/ is never returned
  feed        every feed request signs afresh; nothing serves old signatures
  operators   `manage.py check_media` reports the same from the server side
"""

import io
import logging
from datetime import timedelta
from email.utils import format_datetime
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import MediaStatus, Reel
from api.services import media_availability
from api.tasks import media as media_tasks

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

factory = APIRequestFactory()

OBS = 'https://obs.example/flipstar-media'


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def author():
    return User.objects.create_user(username='availability_author', password='x')


@pytest.fixture
def viewer():
    return User.objects.create_user(username='availability_viewer', password='x')


class FakeOBS:
    """head_object as OBS answers it: 200, or a ClientError with the status --
    a HEAD has no body, so the code is just the number -- and a Date header."""

    def __init__(self):
        self.state = {}  # key -> 'missing' | 'denied' | 'error' | 'down'
        self.heads = []
        self.skew = 0

    def _meta(self, status):
        date = format_datetime(timezone.now() + timedelta(seconds=self.skew), usegmt=True)
        return {'HTTPStatusCode': status, 'HTTPHeaders': {'date': date}}

    def head_object(self, Bucket, Key):
        self.heads.append(Key)
        state = self.state.get(Key)
        if state is None:
            return {'ResponseMetadata': self._meta(200), 'ContentLength': 1}
        if state == 'down':
            raise EndpointConnectionError(endpoint_url='https://obs.example')
        status = {'missing': 404, 'denied': 403, 'error': 503}[state]
        raise ClientError(
            {'Error': {'Code': str(status), 'Message': ''}, 'ResponseMetadata': self._meta(status)},
            'HeadObject',
        )


def signed(key, issued=None, lifetime=3600):
    stamp = (issued or timezone.now()).strftime('%Y%m%dT%H%M%SZ')
    return (
        f'{OBS}/{key}?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=key%2F20260913'
        f'&X-Amz-Date={stamp}&X-Amz-Expires={lifetime}&X-Amz-SignedHeaders=host'
        f'&X-Amz-Signature=sig{stamp}'
    )


@pytest.fixture
def private_obs(settings, monkeypatch):
    """A private bucket, as staging runs: every URL signed, HEAD answered by
    FakeOBS."""
    from django.core.files.storage import default_storage

    settings.S3_BUCKET_NAME = 'flipstar-media'
    settings.S3_ENDPOINT_URL = 'https://obs.example'
    settings.S3_CUSTOM_DOMAIN = 'obs.example'
    settings.AWS_QUERYSTRING_AUTH = True
    settings.AWS_QUERYSTRING_EXPIRE = 3600
    monkeypatch.setattr(default_storage, 'url', lambda key: signed(key))
    obs = FakeOBS()
    monkeypatch.setattr(media_availability, 'storage_client', lambda: obs)
    queued = []
    monkeypatch.setattr(
        media_tasks.process_reel_media, 'delay', lambda pk, force=False: queued.append((pk, force))
    )
    return SimpleNamespace(obs=obs, queued=queued)


def ready_video(user, version=1, **extra):
    n = Reel.objects.count() + 1
    base = f'{OBS}/processed/videos/{n}/v{version}'
    return Reel.objects.create(
        user=user,
        media=f'{base}/720p.mp4',
        media_480=f'{base}/480p.mp4',
        media_360=f'{base}/360p.mp4',
        thumbnail=f'{OBS}/processed/thumbnails/{n}/v{version}/thumb.jpg',
        original_media=f'source/videos/{user.pk}/orig{n}.mp4',
        processed_at=timezone.now(),
        media_version=version,
        **extra,
    )


def key_of(url):
    return url.split('?', 1)[0][len(OBS) + 1 :]


def refresh(user, ids=(), failures=()):
    from api.views.core import refresh_post_media

    request = factory.post(
        '/posts/media/', {'ids': list(ids), 'failures': list(failures)}, format='json'
    )
    if user is not None:
        force_authenticate(request, user=user)
    response = refresh_post_media(request)
    assert response.status_code == 200, response.data
    return response.data


def only(data):
    assert len(data['posts']) == 1, data
    return data['posts'][0]


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


def test_refresh_signs_the_media_now(author, viewer, private_obs):
    import json

    post = ready_video(author)
    data = refresh(viewer, ids=[post.pk])

    row = only(data)
    assert data['expires_in'] == 3600
    assert row['processing_status'] == 'READY' and row['media_type'] == 'video'
    assert key_of(row['media']) == key_of(str(post.media))
    assert media_availability.signature_expiry(row['media']) > timezone.now() + timedelta(
        minutes=59
    ), 'handed out a URL that is about to stop working'
    assert set(row['media_variants']) == {'360', '480'}
    assert row['media_check'] is None
    assert private_obs.obs.heads == [], 'a plain refresh asked storage about every file'
    assert 'source/' not in json.dumps(data, default=str)


def test_an_anonymous_viewer_can_refresh_a_public_post(author, private_obs):
    post = ready_video(author)
    assert only(refresh(None, ids=[post.pk]))['id'] == post.pk


def test_the_feed_signs_afresh_on_every_request(author, viewer, settings, monkeypatch):
    """What a reload gets: nothing on the server hands out old signatures."""
    from django.core.files.storage import default_storage

    from api.views.core import ReelViewSet

    settings.S3_BUCKET_NAME = 'flipstar-media'
    settings.S3_ENDPOINT_URL = 'https://obs.example'
    settings.AWS_QUERYSTRING_AUTH = True
    clock = {'now': timezone.now() - timedelta(hours=2)}
    monkeypatch.setattr(default_storage, 'url', lambda key: signed(key, issued=clock['now']))
    ready_video(author)

    def feed():
        request = factory.get('/reels/')
        force_authenticate(request, user=viewer)
        data = ReelViewSet.as_view({'get': 'list'})(request).data
        rows = data.get('results', data) if isinstance(data, dict) else data
        return rows[0]['media']

    first = feed()
    clock['now'] = timezone.now()
    second = feed()
    assert first != second
    assert media_availability.signature_expiry(second) > timezone.now()


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------


def test_an_expired_url_is_explained_and_replaced(author, viewer, private_obs, caplog):
    post = ready_video(author)
    stale = signed(key_of(str(post.media_480)), issued=timezone.now() - timedelta(hours=2))

    with caplog.at_level(logging.INFO, logger='api.services.media_availability'):
        row = only(
            refresh(
                viewer, failures=[{'id': post.pk, 'url': stale, 'error': '4', 'surface': 'reels'}]
            )
        )

    assert row['media_check'] == {'reason': 'expired_signature', 'repairing': False}
    assert row['media_variants']['480'] != stale
    assert media_availability.signature_expiry(row['media_variants']['480']) > timezone.now()
    assert private_obs.obs.heads == [], 'an expired signature needs no storage request'
    line = next(r.getMessage() for r in caplog.records if 'media.unavailable' in r.getMessage())
    assert f'reel={post.pk}' in line and 'field=media_480' in line
    assert 'reason=expired_signature' in line and 'surface=reels' in line and 'error=4' in line
    assert 'X-Amz-Signature' not in line and 'sig' not in line.split('key=')[1]


def test_a_url_for_replaced_media_is_superseded(author, viewer, private_obs):
    """Edited or re-processed since the client fetched it: its v1 files are gone."""
    post = ready_video(author, version=2)
    old = signed(f'processed/videos/{post.pk}/v1/720p.mp4')

    row = only(refresh(viewer, failures=[{'id': post.pk, 'url': old}]))

    assert row['media_check']['reason'] == 'superseded'
    assert f'/processed/videos/{post.pk}/v2/' in row['media']


def test_a_missing_rendition_is_left_out_and_the_post_repaired(author, viewer, private_obs, caplog):
    post = ready_video(author)
    missing = key_of(str(post.media_480))
    private_obs.obs.state[missing] = 'missing'
    failure = {'id': post.pk, 'url': signed(missing), 'error': '4', 'surface': 'home'}

    with caplog.at_level(logging.INFO, logger='api.services.media_availability'):
        row = only(refresh(viewer, failures=[failure]))

    assert row['media_check'] == {'reason': 'object_missing', 'repairing': True}
    assert row['media_variants'] == {'360': row['media_variants']['360']}, 'offered a missing file'
    assert key_of(row['media']) == key_of(str(post.media))
    assert private_obs.queued == [(post.pk, True)]
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any(
        'reason=object_missing' in r.getMessage() and 'status=404' in r.getMessage() for r in errors
    )

    # Another viewer reporting the same post does not queue it again, nor ask
    # storage again within the minute.
    heads = len(private_obs.obs.heads)
    refresh(author, failures=[failure])
    assert private_obs.queued == [(post.pk, True)]
    assert len(private_obs.obs.heads) == heads


def test_a_post_whose_files_are_all_gone_has_nothing_to_play(author, viewer, private_obs):
    post = ready_video(author)
    for field in ('media', 'media_480', 'media_360', 'thumbnail'):
        private_obs.obs.state[key_of(str(getattr(post, field)))] = 'missing'

    row = only(refresh(viewer, failures=[{'id': post.pk, 'url': signed(key_of(str(post.media)))}]))

    assert row['media'] is None and row['media_variants'] is None and row['thumbnail'] is None
    assert row['media_check'] == {'reason': 'object_missing', 'repairing': True}


def test_a_primary_that_is_gone_falls_back_to_a_rung_that_is_not(author, viewer, private_obs):
    post = ready_video(author)
    private_obs.obs.state[key_of(str(post.media))] = 'missing'

    row = only(refresh(viewer, failures=[{'id': post.pk, 'url': signed(key_of(str(post.media)))}]))

    assert key_of(row['media']) == key_of(str(post.media_480))


@pytest.mark.parametrize(
    'state, reason, status',
    [
        ('denied', 'access_denied', 403),
        ('error', 'storage_error', 503),
        ('down', 'storage_error', None),
    ],
)
def test_storage_trouble_is_named(author, viewer, private_obs, caplog, state, reason, status):
    post = ready_video(author)
    key = key_of(str(post.media))
    private_obs.obs.state[key] = state

    with caplog.at_level(logging.INFO, logger='api.services.media_availability'):
        row = only(refresh(viewer, failures=[{'id': post.pk, 'url': signed(key)}]))

    assert row['media_check']['reason'] == reason
    assert row['media'], 'the post lost its media over a storage hiccup'
    line = next(r for r in caplog.records if 'media.unavailable' in r.getMessage())
    assert line.levelno == logging.ERROR
    assert f'status={status if status else "-"}' in line.getMessage()
    assert private_obs.queued == [], 'repaired a post whose files may be fine'


def test_clocks_apart_are_named(author, viewer, private_obs):
    post = ready_video(author)
    private_obs.obs.skew = 20 * 60

    row = only(refresh(viewer, failures=[{'id': post.pk, 'url': signed(key_of(str(post.media)))}]))

    assert row['media_check']['reason'] == 'clock_skew'


def test_nothing_wrong_on_the_server_says_so(author, viewer, private_obs):
    """The object is there and the URL in date: a network or codec problem in
    the browser. The client gets a fresh URL to try once more."""
    post = ready_video(author)

    row = only(refresh(viewer, failures=[{'id': post.pk, 'url': signed(key_of(str(post.media)))}]))

    assert row['media_check']['reason'] == 'available'


def test_an_unsigned_url_into_the_private_bucket_is_named(author, viewer, private_obs):
    post = ready_video(author)
    row = only(refresh(viewer, failures=[{'id': post.pk, 'url': str(post.media)}]))
    assert row['media_check']['reason'] == 'unsigned'


def test_a_url_into_the_originals_is_named_and_never_answered_with_one(author, viewer, private_obs):
    import json

    post = ready_video(author)
    data = refresh(viewer, failures=[{'id': post.pk, 'url': signed(post.original_media)}])

    assert only(data)['media_check']['reason'] == 'original_requested'
    assert 'source/' not in json.dumps(data, default=str)


def test_a_crafted_url_cannot_forge_a_log_line(author, viewer, private_obs, caplog):
    post = ready_video(author)
    crafted = f'{OBS}/processed/videos/{post.pk}/v9/x.mp4%0Amedia.unavailable%20reel=1%20reason=ok'

    with caplog.at_level(logging.INFO, logger='api.services.media_availability'):
        refresh(
            viewer,
            failures=[{'id': post.pk, 'url': crafted, 'surface': 'x\nforged', 'error': '4\r'}],
        )

    lines = [r.getMessage() for r in caplog.records if 'media.unavailable' in r.getMessage()]
    assert len(lines) == 1 and '\n' not in lines[0] and '\r' not in lines[0], lines


def test_someone_elses_url_is_external(author, viewer, private_obs):
    post = ready_video(author)
    row = only(
        refresh(viewer, failures=[{'id': post.pk, 'url': 'https://res.cloudinary.com/x/clip.mp4'}])
    )
    assert row['media_check']['reason'] == 'external'


# ---------------------------------------------------------------------------
# Who may see what
# ---------------------------------------------------------------------------


def test_processing_posts_are_the_authors_alone(author, viewer, private_obs):
    post = ready_video(author, processing_status=MediaStatus.PROCESSING)

    assert refresh(viewer, ids=[post.pk])['posts'] == []
    own = only(refresh(author, failures=[{'id': post.pk, 'url': 'https://obs.example/x'}]))
    assert own['processing_status'] == 'PROCESSING' and own['media'] is None
    assert own['media_check']['reason'] == 'not_ready'


def test_moderation_applies_as_in_the_feed(author, viewer, private_obs):
    hidden = ready_video(author, is_hidden=True)
    shadowed = ready_video(author)
    author.profile.is_shadowbanned = True
    author.profile.save(update_fields=['is_shadowbanned'])

    assert refresh(viewer, ids=[hidden.pk, shadowed.pk])['posts'] == []
    assert refresh(None, ids=[shadowed.pk])['posts'] == []
    assert [p['id'] for p in refresh(author, ids=[shadowed.pk])['posts']] == [shadowed.pk]


def test_limits_and_garbage(author, viewer, private_obs):
    posts = [ready_video(author) for _ in range(22)]
    data = refresh(viewer, ids=[p.pk for p in posts] + ['x', -1, None, '12' * 9])
    assert len(data['posts']) == 20

    from api.views.core import refresh_post_media

    request = factory.post('/posts/media/', {'ids': 'nope', 'failures': 'nope'}, format='json')
    force_authenticate(request, user=viewer)
    assert refresh_post_media(request).data == {'posts': [], 'expires_in': None}


# ---------------------------------------------------------------------------
# Pieces
# ---------------------------------------------------------------------------


def test_signature_expiry_reads_both_signing_forms():
    issued = timezone.now().replace(microsecond=0)
    assert media_availability.signature_expiry(signed('a.mp4', issued, 600)) == issued + timedelta(
        seconds=600
    )
    v2 = f'{OBS}/a.mp4?AWSAccessKeyId=k&Signature=s&Expires=1789000000'
    assert media_availability.signature_expiry(v2).timestamp() == 1789000000
    assert media_availability.signature_expiry(f'{OBS}/a.mp4') is None
    assert media_availability.signature_expiry('not a url') is None


def test_the_signed_url_lifetime_is_a_setting(monkeypatch):
    from infrastructure.storage.config import apply_storage_settings

    for key, value in {
        'ACCESS_KEY_ID': 'k',
        'SECRET_ACCESS_KEY': 's',
        'STORAGE_BUCKET_NAME': 'flipstar-media',
        'S3_ENDPOINT_URL': 'https://obs.example',
        'S3_DEFAULT_ACL': '',
    }.items():
        monkeypatch.setenv(key, value)
    assert apply_storage_settings('/media/')['querystring_expire'] == 3600
    monkeypatch.setenv('S3_QUERYSTRING_EXPIRE', '21600')
    assert apply_storage_settings('/media/')['querystring_expire'] == 21600
    monkeypatch.setenv('S3_QUERYSTRING_EXPIRE', '99999999')
    assert apply_storage_settings('/media/')['querystring_expire'] == 7 * 24 * 3600


def test_check_media_reports_what_storage_is_missing(author, private_obs):
    post = ready_video(author)
    healthy = ready_video(author)
    private_obs.obs.state[key_of(str(post.media_360))] = 'missing'
    private_obs.obs.state[key_of(str(post.thumbnail))] = 'denied'

    out = io.StringIO()
    call_command('check_media', stdout=out)
    report = out.getvalue()

    assert 'media URLs: signed, valid for 3600 s' in report
    assert f'post {post.pk}: media_360 missing 404' in report
    assert f'post {post.pk}: thumbnail denied 403' in report
    assert f'post {healthy.pk}:' not in report
    assert 'missing 1, denied 1' in report
    assert private_obs.queued == []

    call_command('check_media', '--repair', stdout=io.StringIO())
    assert private_obs.queued == [(post.pk, True)]


def test_check_media_flags_clocks_apart(author, private_obs):
    ready_video(author)
    private_obs.obs.skew = -30 * 60
    out = io.StringIO()
    call_command('check_media', stdout=out)
    assert 'signed URLs will be refused' in out.getvalue()
