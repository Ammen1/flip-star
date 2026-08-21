"""
Regression tests for DraftViewSet (api/views/core.py) -- ported from the
master branch, entirely missing in the current project before this change
(no Draft model, serializer, or viewset at all).

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.core import Draft
from api.views.core import DraftViewSet

pytestmark = pytest.mark.integration

factory = APIRequestFactory()


@pytest.fixture
def user(db):
    u = User.objects.create_user(username='draft_user', password='x')
    yield u
    u.delete()


@pytest.fixture
def other_user(db):
    u = User.objects.create_user(username='draft_other_user', password='x')
    yield u
    u.delete()


def test_create_draft(user):
    request = factory.post('/drafts/', {'caption': 'work in progress', 'hashtags': '#draft'}, format='json')
    force_authenticate(request, user=user)

    response = DraftViewSet.as_view({'post': 'create'})(request)

    assert response.status_code == 201, response.data
    assert Draft.objects.filter(user=user, caption='work in progress').exists()


def test_list_drafts_only_returns_own(user, other_user):
    Draft.objects.create(user=user, caption='mine')
    Draft.objects.create(user=other_user, caption='not mine')

    request = factory.get('/drafts/')
    force_authenticate(request, user=user)

    response = DraftViewSet.as_view({'get': 'list'})(request)

    assert response.status_code == 200
    captions = {d['caption'] for d in response.data}
    assert captions == {'mine'}


def test_update_own_draft(user):
    draft = Draft.objects.create(user=user, caption='old caption')

    request = factory.patch(f'/drafts/{draft.id}/', {'caption': 'new caption'}, format='json')
    force_authenticate(request, user=user)

    response = DraftViewSet.as_view({'patch': 'update'})(request, pk=draft.id)

    assert response.status_code == 200, response.data
    draft.refresh_from_db()
    assert draft.caption == 'new caption'


def test_cannot_update_another_users_draft(user, other_user):
    draft = Draft.objects.create(user=other_user, caption='not yours')

    request = factory.patch(f'/drafts/{draft.id}/', {'caption': 'hijacked'}, format='json')
    force_authenticate(request, user=user)

    response = DraftViewSet.as_view({'patch': 'update'})(request, pk=draft.id)

    assert response.status_code == 404
    draft.refresh_from_db()
    assert draft.caption == 'not yours'


def test_destroy_own_draft(user):
    draft = Draft.objects.create(user=user, caption='delete me')

    request = factory.delete(f'/drafts/{draft.id}/')
    force_authenticate(request, user=user)

    response = DraftViewSet.as_view({'delete': 'destroy'})(request, pk=draft.id)

    assert response.status_code == 200, response.data
    assert not Draft.objects.filter(id=draft.id).exists()


def test_cannot_destroy_another_users_draft(user, other_user):
    draft = Draft.objects.create(user=other_user, caption='not yours')

    request = factory.delete(f'/drafts/{draft.id}/')
    force_authenticate(request, user=user)

    response = DraftViewSet.as_view({'delete': 'destroy'})(request, pk=draft.id)

    assert response.status_code == 404
    assert Draft.objects.filter(id=draft.id).exists()


def test_anonymous_cannot_list_drafts(db):
    request = factory.get('/drafts/')

    response = DraftViewSet.as_view({'get': 'list'})(request)

    assert response.status_code == 401
