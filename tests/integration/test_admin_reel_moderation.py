"""
Regression tests for admin_reel_detail / admin_reel_moderate (api/views/admin.py)
-- ported from the master branch, entirely missing in the current project
before this change.

Uses the correct required_permission wiring established in item 3
(<view>.view_class.required_permission set at module level), not master's
own broken in-body assignment -- see tests/integration/test_admin_permissions.py
for the proof of why that pattern doesn't work.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.admin import SystemLog
from api.models.core import Reel
from api.views.admin import admin_reel_detail, admin_reel_moderate

pytestmark = pytest.mark.integration

factory = APIRequestFactory()


@pytest.fixture
def admin_user(db):
    from api.models.subscription import AdminRole

    u = User.objects.create_user(username='reel_mod_admin', password='x', is_staff=True)
    AdminRole.objects.create(user=u, role='content_moderator', permission_level='full')
    yield u
    u.delete()


@pytest.fixture
def staff_without_role(db):
    u = User.objects.create_user(username='reel_mod_staff_no_role', password='x', is_staff=True)
    yield u
    u.delete()


@pytest.fixture
def reel(db):
    owner = User.objects.create_user(username='reel_mod_owner', password='x')
    r = Reel.objects.create(user=owner, caption='moderate me')
    yield r
    r.delete()
    owner.delete()


def test_admin_reel_detail_returns_full_info(admin_user, reel):
    request = factory.get(f'/admin/reels/{reel.id}/')
    force_authenticate(request, user=admin_user)

    response = admin_reel_detail(request, reel_id=reel.id)

    assert response.status_code == 200, response.data
    assert response.data['id'] == reel.id
    assert response.data['user']['username'] == 'reel_mod_owner'
    assert response.data['is_hidden'] is False


def test_admin_reel_detail_404_for_unknown_reel(admin_user, db):
    request = factory.get('/admin/reels/999999/')
    force_authenticate(request, user=admin_user)

    response = admin_reel_detail(request, reel_id=999999)

    assert response.status_code == 404


def test_staff_without_role_cannot_view_reel_detail(staff_without_role, reel):
    request = factory.get(f'/admin/reels/{reel.id}/')
    force_authenticate(request, user=staff_without_role)

    response = admin_reel_detail(request, reel_id=reel.id)

    assert response.status_code == 403


def test_admin_reel_moderate_remove_hides_reel(admin_user, reel):
    request = factory.post(f'/admin/reels/{reel.id}/moderate/', {'action': 'remove'}, format='json')
    force_authenticate(request, user=admin_user)

    response = admin_reel_moderate(request, reel_id=reel.id)

    assert response.status_code == 200, response.data
    reel.refresh_from_db()
    assert reel.is_hidden is True

    log = SystemLog.objects.filter(log_type='admin_action', details__reel_id=reel.id).first()
    assert log is not None
    assert log.details['action'] == 'reel_remove'


def test_admin_reel_moderate_approve_unhides_reel(admin_user, reel):
    reel.is_hidden = True
    reel.save(update_fields=['is_hidden'])

    request = factory.post(f'/admin/reels/{reel.id}/moderate/', {'action': 'approve'}, format='json')
    force_authenticate(request, user=admin_user)

    response = admin_reel_moderate(request, reel_id=reel.id)

    assert response.status_code == 200, response.data
    reel.refresh_from_db()
    assert reel.is_hidden is False


def test_admin_reel_moderate_rejects_invalid_action(admin_user, reel):
    request = factory.post(f'/admin/reels/{reel.id}/moderate/', {'action': 'nonsense'}, format='json')
    force_authenticate(request, user=admin_user)

    response = admin_reel_moderate(request, reel_id=reel.id)

    assert response.status_code == 400
    reel.refresh_from_db()
    assert reel.is_hidden is False


def test_staff_without_role_cannot_moderate_reel(staff_without_role, reel):
    request = factory.post(f'/admin/reels/{reel.id}/moderate/', {'action': 'remove'}, format='json')
    force_authenticate(request, user=staff_without_role)

    response = admin_reel_moderate(request, reel_id=reel.id)

    assert response.status_code == 403
    reel.refresh_from_db()
    assert reel.is_hidden is False
