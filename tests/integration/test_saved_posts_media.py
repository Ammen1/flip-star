"""
Saved posts must come back as full feed entries, media included.

What was wrong
--------------
The web Saved grid called ``GET /saved/``, whose ``SavedPostSerializer``
returns bare rows -- ``{id, user, reel: <pk>, created_at}`` -- so the grid saw
no ``image``/``media``/``thumbnail`` and rendered every tile as "No media".

The backend already had the right shape under ``GET /reels/saved/``: the same
``ReelSerializer`` plus ``build_feed_context`` that the following/trending
feeds use, which is what the mobile app reads. These pin that contract so the
web client keeps getting media-bearing reel objects for its Saved grid.
"""

import fakeredis
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import Reel, SavedPost
from api.models.core import MediaStatus
from common.security.e2e_encryption import generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


@pytest.fixture
def server_keys(db):
    """reels_saved carries @encrypted_endpoint, so the server needs keys."""
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def client_keys():
    return generate_keypair()


@pytest.fixture
def author():
    return User.objects.create_user(username='saved_author', password='x')


@pytest.fixture
def viewer():
    return User.objects.create_user(username='saved_viewer', password='x')


def saved(viewer, client_keys):
    from api.views.reels import reels_saved

    client_public_key, _ = client_keys
    request = factory.get('/reels/saved/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)
    force_authenticate(request, user=viewer)
    response = reels_saved(request)
    assert response.status_code == 200, response.data
    return response.data


def image_reel(author):
    return Reel.objects.create(
        user=author,
        caption='still shot',
        image='reels/photo.jpg',
        # The pipeline publishes thumbnails under the servable processed/
        # prefix, so `thumbnails/...` alone would be treated as unsupported.
        thumbnail='processed/thumbnails/photo.jpg',
        processing_status=MediaStatus.READY,
    )


def video_reel(author):
    return Reel.objects.create(
        user=author,
        caption='moving frame',
        media='reels/clip.mp4',
        image='reels/poster.jpg',
        thumbnail='processed/thumbnails/clip.jpg',
        processing_status=MediaStatus.READY,
    )


def save(viewer, reel):
    return SavedPost.objects.create(user=viewer, reel=reel)


def test_saved_image_reels_carry_the_image_contract(
    author, viewer, server_keys, client_keys
):
    reel = image_reel(author)
    save(viewer, reel)

    rows = {row['id']: row for row in saved(viewer, client_keys)}

    assert reel.id in rows
    row = rows[reel.id]
    assert row['media_type'] == 'image'
    assert row['image'], 'grid needs an image URL, not a bare reel pk'
    assert row['image'] != str(reel.id)
    assert row['thumbnail'], 'tile shows the smallest rendition'
    assert 'media' not in row or row['media'] is None


def test_saved_video_reels_carry_the_video_contract(
    author, viewer, server_keys, client_keys
):
    reel = video_reel(author)
    save(viewer, reel)

    rows = {row['id']: row for row in saved(viewer, client_keys)}

    assert reel.id in rows
    row = rows[reel.id]
    assert row['media_type'] == 'video'
    assert row['media'], 'video saved posts must carry the playable transcode'
    assert row['thumbnail'], 'video tile needs its poster'
    assert row['image'], 'fallback still for tiles that cannot decode WebP'


def test_unsaved_reels_are_not_returned(author, viewer, server_keys, client_keys):
    saved_reel = image_reel(author)
    unsaved_reel = video_reel(author)
    save(viewer, saved_reel)

    returned = {row['id'] for row in saved(viewer, client_keys)}

    assert saved_reel.id in returned
    assert unsaved_reel.id not in returned, 'only the viewer favourite appears'


def test_saved_but_not_ready_reels_are_left_out(
    author, viewer, server_keys, client_keys
):
    """A reel still processing has no media to serve, exactly like the feeds:
    it waits until READY instead of surfacing a media-less tile."""
    reel = Reel.objects.create(
        user=author,
        caption='still encoding',
        image='reels/original.jpg',
        processing_status=MediaStatus.PROCESSING,
    )
    save(viewer, reel)

    assert saved(viewer, client_keys) == []