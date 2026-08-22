"""
Regression tests for common/permissions/roles.py::HasAdminPermission --
restores per-action admin authorization against AdminRole that api/views/admin.py
had regressed to a blanket IsAdminUser (is_staff-only) check.

Uses the real view functions and the real DRF permission-checking pipeline
(APIRequestFactory + view_class.required_permission), not a reproduction --
this is specifically testing that the attribute-setting mechanism actually
works, since the equivalent pattern on the `master` branch (setting
`view.required_permission = ...` inside the function body) does not: DRF
checks permissions before the handler body ever runs, so that assignment
is never visible to the permission class. See this file's own tests for
the isolated proof, and api/views/admin.py's module-level
`<view>.view_class.required_permission = '...'` assignments for the fix.

The 0063_add_mentions dependency bug that used to make MIGRATIONS_ARE_REPLAYABLE
False (see tests/conftest.py) has been fixed, so this uses the real `db`
fixture -- pytest-django provisions a freshly migrated database per test.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

pytestmark = pytest.mark.integration


@pytest.fixture
def staff_user(db):
    u = User.objects.create_user(username='admin_perm_staff', password='x', is_staff=True)
    yield u
    u.delete()


@pytest.fixture
def content_moderator(db):
    from api.models.subscription import AdminRole

    u = User.objects.create_user(username='admin_perm_moderator', password='x', is_staff=True)
    AdminRole.objects.create(user=u, role='content_moderator', permission_level='full')
    yield u
    u.delete()


# ---------------------------------------------------------------------------
# The mechanism itself: view_class.required_permission is actually visible
# at permission-check time (unlike master's in-body assignment, proven
# broken separately below).
# ---------------------------------------------------------------------------

def test_required_permission_set_via_view_class_is_visible_at_check_time():
    from common.permissions import HasAdminPermission

    seen = {}

    class _Probe(HasAdminPermission):
        def has_permission(self, request, view):
            seen['value'] = getattr(view, 'required_permission', 'NOT SET')
            return True

    @api_view(['GET'])
    @permission_classes([_Probe])
    def probe(request):
        return Response({'ok': True})

    probe.view_class.required_permission = 'view_users'

    factory = APIRequestFactory()
    probe(factory.get('/probe/'))

    assert seen['value'] == 'view_users'


def test_master_style_in_body_assignment_is_NOT_visible_at_check_time():
    """Documents exactly why the master-branch pattern doesn't work: DRF's
    check_permissions() runs before the handler body executes, so an
    assignment made inside the function body is never seen -- on the
    first call OR any subsequent one, since @api_view wraps a fresh
    WrappedAPIView class that doesn't expose the original function's
    attributes to has_permission(). This is why api/views/admin.py sets
    required_permission via <view>.view_class.required_permission at
    module level instead."""
    seen = []

    class _Probe(BasePermission):
        def has_permission(self, request, view):
            seen.append(getattr(view, 'required_permission', 'NOT SET'))
            return True

    @api_view(['GET'])
    @permission_classes([_Probe])
    def probe(request):
        probe.required_permission = 'view_users'  # master's actual pattern
        return Response({'ok': True})

    factory = APIRequestFactory()
    request = factory.get('/probe/')
    probe(request)
    probe(request)  # second call -- would pick up a "sticky" attribute if the pattern worked at all

    assert seen == ['NOT SET', 'NOT SET']


# ---------------------------------------------------------------------------
# The actual regression: is_staff alone must not be enough
# ---------------------------------------------------------------------------

def test_staff_without_admin_role_cannot_delete_users(staff_user):
    """is_staff=True + no AdminRole must NOT grant admin_user_delete access
    -- the exact regression this whole fix addresses. Before restoring
    HasAdminPermission, api/views/admin.py's blanket IsAdminUser granted
    this to any staff account regardless of role."""
    from api.views.admin import admin_user_delete

    target = User.objects.create_user(username='admin_perm_target1', password='x')
    factory = APIRequestFactory()
    request = factory.delete(f'/admin/users/{target.id}/')
    force_authenticate(request, user=staff_user)

    response = admin_user_delete(request, user_id=str(target.id))

    assert response.status_code == 403, response.data
    assert User.objects.filter(id=target.id).exists(), 'user must not have been deleted'

    target.delete()


def test_staff_without_admin_role_cannot_view_users_list(staff_user):
    from api.views.admin import admin_users_list

    factory = APIRequestFactory()
    request = factory.get('/admin/users/')
    force_authenticate(request, user=staff_user)

    response = admin_users_list(request)

    assert response.status_code == 403, response.data


def test_content_moderator_can_view_content_but_not_delete_users(content_moderator):
    """A role that grants 'view_content'/'moderate_content' but not
    'delete_users' must be able to use admin_reels_list yet still be
    refused by admin_user_delete -- proves the check is genuinely
    per-action, not all-or-nothing once *any* AdminRole exists."""
    from api.views.admin import admin_reels_list, admin_user_delete

    factory = APIRequestFactory()

    list_request = factory.get('/admin/reels/')
    force_authenticate(list_request, user=content_moderator)
    list_response = admin_reels_list(list_request)
    assert list_response.status_code == 200, list_response.data

    target = User.objects.create_user(username='admin_perm_target2', password='x')
    delete_request = factory.delete(f'/admin/users/{target.id}/')
    force_authenticate(delete_request, user=content_moderator)
    delete_response = admin_user_delete(delete_request, user_id=str(target.id))

    assert delete_response.status_code == 403, delete_response.data
    assert User.objects.filter(id=target.id).exists()

    target.delete()


def test_superuser_bypasses_admin_role_entirely(db):
    from api.views.admin import admin_user_delete

    superuser = User.objects.create_superuser(username='admin_perm_super', password='x', email='s@example.com')
    target = User.objects.create_user(username='admin_perm_target3', password='x')

    factory = APIRequestFactory()
    request = factory.delete(f'/admin/users/{target.id}/')
    force_authenticate(request, user=superuser)

    response = admin_user_delete(request, user_id=str(target.id))

    assert response.status_code == 200, response.data
    assert not User.objects.filter(id=target.id).exists()

    superuser.delete()
