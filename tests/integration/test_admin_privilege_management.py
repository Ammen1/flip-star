"""
Regression tests for the admin privilege-management endpoints
(api/views/admin.py: admin_user_role, admin_user_logs, admin_grant_admin,
admin_privilege_audit) -- ported from the master branch, entirely missing in
the current project before this change, along with their backing model
(api.models.admin.PrivilegeAuditLog).

Master declares PrivilegeAuditLog but never writes to it anywhere in the
codebase -- admin_user_logs/admin_privilege_audit would always render empty
in master. The port fixes that by having admin_grant_admin actually create
PrivilegeAuditLog rows on grant/revoke, alongside the existing SystemLog
admin_action entry.

Master also gates admin_privilege_audit behind bare IsAdminUser (any
is_staff=True account), letting any staff user read every admin grant/revoke
action including phone numbers and emails. The port gates it behind
HasAdminPermission('manage_admins'), matching admin_grant_admin -- see the
tests proving a content_moderator (a real role, but not manage_admins) is
refused.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.admin import PrivilegeAuditLog
from api.models.subscription import AdminRole
from api.views.admin import (
    admin_grant_admin,
    admin_privilege_audit,
    admin_user_logs,
    admin_user_role,
)

pytestmark = pytest.mark.integration

factory = APIRequestFactory()


@pytest.fixture
def superuser(db):
    u = User.objects.create_superuser(username='privaudit_super', password='x', email='s@example.com')
    yield u
    u.delete()


@pytest.fixture
def content_moderator(db):
    u = User.objects.create_user(username='privaudit_moderator', password='x', is_staff=True)
    AdminRole.objects.create(user=u, role='content_moderator', permission_level='full')
    yield u
    u.delete()


@pytest.fixture
def target_user(db):
    u = User.objects.create_user(username='privaudit_target', password='x')
    yield u
    u.delete()


def test_admin_user_role_returns_null_for_user_without_role(superuser, target_user):
    request = factory.get(f'/admin/users/{target_user.id}/admin-role/')
    force_authenticate(request, user=superuser)

    response = admin_user_role(request, user_id=target_user.id)

    assert response.status_code == 200
    assert response.data == {'role': None, 'permission_level': None, 'is_active': None}


def test_admin_user_role_returns_role_details(superuser, target_user):
    AdminRole.objects.create(user=target_user, role='finance_team', permission_level='edit_only')

    request = factory.get(f'/admin/users/{target_user.id}/admin-role/')
    force_authenticate(request, user=superuser)

    response = admin_user_role(request, user_id=target_user.id)

    assert response.status_code == 200
    assert response.data == {'role': 'finance_team', 'permission_level': 'edit_only', 'is_active': True}


def test_admin_grant_admin_creates_role_and_privilege_audit_row(superuser, target_user):
    request = factory.post(
        f'/admin/users/{target_user.id}/grant-admin/',
        {'action': 'grant', 'role': 'support_agent', 'permission_level': 'full'}, format='json',
    )
    force_authenticate(request, user=superuser)

    response = admin_grant_admin(request, user_id=target_user.id)

    assert response.status_code == 200, response.data
    target_user.refresh_from_db()
    assert target_user.is_staff is True
    assert target_user.is_superuser is False

    role = AdminRole.objects.get(user=target_user)
    assert role.role == 'support_agent'
    assert role.permission_level == 'full'

    audit_row = PrivilegeAuditLog.objects.get(target_user_id=target_user.id)
    assert audit_row.action == 'GRANT'
    assert audit_row.performed_by == superuser.username


def test_admin_grant_admin_super_admin_role_sets_is_superuser(superuser, target_user):
    request = factory.post(
        f'/admin/users/{target_user.id}/grant-admin/',
        {'action': 'grant', 'role': 'super_admin', 'permission_level': 'full'}, format='json',
    )
    force_authenticate(request, user=superuser)

    admin_grant_admin(request, user_id=target_user.id)

    target_user.refresh_from_db()
    assert target_user.is_superuser is True


def test_admin_grant_admin_revoke_clears_role_and_flags(superuser, target_user):
    AdminRole.objects.create(user=target_user, role='support_agent', permission_level='full')
    target_user.is_staff = True
    target_user.save()

    request = factory.post(f'/admin/users/{target_user.id}/grant-admin/', {'action': 'revoke'}, format='json')
    force_authenticate(request, user=superuser)

    response = admin_grant_admin(request, user_id=target_user.id)

    assert response.status_code == 200, response.data
    target_user.refresh_from_db()
    assert target_user.is_staff is False
    assert AdminRole.objects.filter(user=target_user).exists() is False

    audit_row = PrivilegeAuditLog.objects.get(target_user_id=target_user.id, action='REVOKE')
    assert audit_row.performed_by == superuser.username


def test_admin_grant_admin_404_for_unknown_user(superuser, db):
    request = factory.post('/admin/users/999999/grant-admin/', {'action': 'grant'}, format='json')
    force_authenticate(request, user=superuser)

    response = admin_grant_admin(request, user_id=999999)

    assert response.status_code == 404


def test_content_moderator_cannot_grant_admin(content_moderator, target_user):
    """manage_admins is granted to none of the 3 non-super_admin roles --
    matches master's own role_permissions design (only super_admin manages
    admin access)."""
    request = factory.post(
        f'/admin/users/{target_user.id}/grant-admin/', {'action': 'grant', 'role': 'support_agent'}, format='json',
    )
    force_authenticate(request, user=content_moderator)

    response = admin_grant_admin(request, user_id=target_user.id)

    assert response.status_code == 403
    assert not AdminRole.objects.filter(user=target_user).exists()


def test_admin_user_logs_returns_entries_for_target_and_actor(superuser, target_user):
    PrivilegeAuditLog.objects.create(
        action='GRANT', target_user=target_user.username, target_user_id=target_user.id,
        performed_by=superuser.username, performed_by_id=superuser.id, details='granted',
    )

    request = factory.get(f'/admin/users/{target_user.id}/logs/')
    force_authenticate(request, user=superuser)

    response = admin_user_logs(request, user_id=target_user.id)

    assert response.status_code == 200
    assert len(response.data['logs']) == 1
    assert response.data['logs'][0]['action'] == 'GRANT'


def test_admin_privilege_audit_lists_all_entries(superuser, target_user):
    PrivilegeAuditLog.objects.create(
        action='GRANT', target_user=target_user.username, target_user_id=target_user.id,
        performed_by=superuser.username, performed_by_id=superuser.id, details='granted',
    )

    request = factory.get('/admin/privilege-audit/')
    force_authenticate(request, user=superuser)

    response = admin_privilege_audit(request)

    assert response.status_code == 200
    assert response.data['total'] == 1
    assert response.data['logs'][0]['target_user'] == target_user.username
    assert response.data['logs'][0]['performed_by'] == superuser.username


def test_content_moderator_cannot_view_privilege_audit(content_moderator, db):
    """The audit trail of who granted/revoked admin access is nearly as
    sensitive as being in it -- master's bare IsAdminUser would let any
    staff account read it; this must not."""
    request = factory.get('/admin/privilege-audit/')
    force_authenticate(request, user=content_moderator)

    response = admin_privilege_audit(request)

    assert response.status_code == 403
