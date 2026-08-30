"""
Posting a video requires an active subscription -- enforced server-side.

The client also checks, but the client is a courtesy: a subscription can lapse
between opening the create page and pressing Publish, and the endpoint is
reachable directly. What matters here is not only *that* the request is
refused, but the *shape* of the refusal: the frontend keeps the user's video
and caption only when it can recognise this case by `code`, so these tests pin
the contract the post page branches on.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.core import Subscription
from api.services.subscription_access import has_active_subscription
from api.views.core import create_post

pytestmark = pytest.mark.integration

factory = APIRequestFactory()

MP4_BYTES = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 64


@pytest.fixture
def user(db):
    u = User.objects.create_user(username='gate_user', password='x')
    yield u
    u.delete()


def set_subscription_expiry(user, expires_at):
    """Subscription.user is a OneToOne and a row already exists for every user,
    so update rather than create."""
    obj, _ = Subscription.objects.update_or_create(
        user=user, defaults={'plan': 'pro', 'expires_at': expires_at}
    )
    return obj


def subscribe(user, *, days=30):
    return set_subscription_expiry(user, timezone.now() + timedelta(days=days))


def video_file(name='clip.mp4', content_type='video/mp4'):
    return SimpleUploadedFile(name, MP4_BYTES, content_type=content_type)


def post_video(user, upload):
    request = factory.post('/posts/', {'caption': 'my clip', 'file': upload})
    force_authenticate(request, user=user)
    return create_post(request)


# ─── the refusal ──────────────────────────────────────────────────────────────

def test_unsubscribed_user_cannot_post_a_video(user):
    response = post_video(user, video_file())
    assert response.status_code == 403, response.data


def test_the_refusal_carries_the_code_the_client_branches_on(user):
    """Without this exact shape the post page shows a generic error and the
    user's recording is thrown away -- the bug this gate exists to prevent."""
    response = post_video(user, video_file())

    assert response.data['success'] is False
    assert response.data['code'] == 'SUBSCRIPTION_REQUIRED'
    assert isinstance(response.data['message'], str) and response.data['message']


def test_an_expired_subscription_is_not_an_active_one(user):
    set_subscription_expiry(user, timezone.now() - timedelta(seconds=1))
    response = post_video(user, video_file())
    assert response.status_code == 403
    assert response.data['code'] == 'SUBSCRIPTION_REQUIRED'


@pytest.mark.parametrize(
    'name,content_type',
    [
        ('clip.mp4', 'video/mp4'),
        ('clip.webm', 'video/webm'),
        ('clip.mov', 'video/quicktime'),
        # Extension alone is enough -- a mislabelled content type must not slip past.
        ('clip.mkv', 'application/octet-stream'),
        ('CLIP.MP4', 'application/octet-stream'),
    ],
)
def test_every_video_form_is_gated(user, name, content_type):
    response = post_video(user, SimpleUploadedFile(name, MP4_BYTES, content_type=content_type))
    assert response.status_code == 403, f'{name} slipped past the gate'
    assert response.data['code'] == 'SUBSCRIPTION_REQUIRED'


# ─── what the gate must NOT block ─────────────────────────────────────────────

def test_a_subscriber_is_not_blocked(user):
    subscribe(user)
    response = post_video(user, video_file())
    assert response.status_code != 403, response.data
    assert (response.data or {}).get('code') != 'SUBSCRIPTION_REQUIRED'


def test_images_are_not_gated(user):
    """The rule is about video. An unsubscribed user posting a photo must not
    be caught by it."""
    image = SimpleUploadedFile('pic.jpg', b'\xff\xd8\xff' + b'\x00' * 32, content_type='image/jpeg')
    request = factory.post('/posts/', {'caption': 'a photo', 'file': image})
    force_authenticate(request, user=user)
    response = create_post(request)

    assert (response.data or {}).get('code') != 'SUBSCRIPTION_REQUIRED'
    assert response.status_code != 403


# ─── the predicate on its own ─────────────────────────────────────────────────

def test_predicate_is_false_without_a_subscription(user):
    assert has_active_subscription(user) is False


def test_predicate_is_true_with_a_live_subscription(user):
    subscribe(user)
    assert has_active_subscription(user) is True


def test_predicate_rejects_anonymous_and_none(db):
    from django.contrib.auth.models import AnonymousUser

    assert has_active_subscription(None) is False
    assert has_active_subscription(AnonymousUser()) is False
