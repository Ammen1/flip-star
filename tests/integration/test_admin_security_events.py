"""
Regression tests for the admin SecurityEvent management endpoints
(api/views/admin.py) -- ported from the master branch, entirely missing in
the current project before this change. These are the read/manage
counterpart to the SecurityEvent rows common/middleware/security.py writes
(see tests/integration/test_security_event_logging.py).

Uses the correct required_permission wiring established in item 3
(<view>.view_class.required_permission set at module level). None of the
4 non-super_admin roles (support_agent/finance_team/content_moderator) are
granted view_security_events/manage_security_events -- matching master's
own role_permissions, which also never grants these to anything but
super_admin -- so a non-superuser admin (even with a role) must be refused.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.admin import SecurityEvent
from api.views.admin import (
    admin_log_security_event,
    admin_mark_all_security_events_read,
    admin_resolve_security_event,
    admin_security_events,
    admin_security_stats,
)

pytestmark = pytest.mark.integration

factory = APIRequestFactory()


@pytest.fixture
def superuser(db):
    u = User.objects.create_superuser(username='secevt_super', password='x', email='s@example.com')
    yield u
    u.delete()


@pytest.fixture
def content_moderator(db):
    from api.models.subscription import AdminRole

    u = User.objects.create_user(username='secevt_moderator', password='x', is_staff=True)
    AdminRole.objects.create(user=u, role='content_moderator', permission_level='full')
    yield u
    u.delete()


@pytest.fixture
def unresolved_event(db):
    event = SecurityEvent.objects.create(
        event_type='SCANNER_PROBE', severity='LOW', username='Anonymous', endpoint='/.env', is_resolved=False,
    )
    yield event
    event.delete()


def test_admin_security_events_lists_events(superuser, unresolved_event):
    request = factory.get('/admin/security-events/')
    force_authenticate(request, user=superuser)

    response = admin_security_events(request)

    assert response.status_code == 200
    assert response.data['total'] == 1
    assert response.data['events'][0]['id'] == unresolved_event.id


def test_admin_security_events_filters_by_severity(superuser, unresolved_event):
    SecurityEvent.objects.create(event_type='PERMISSION_DENIED', severity='HIGH', username='u', endpoint='/x')

    request = factory.get('/admin/security-events/?severity=HIGH')
    force_authenticate(request, user=superuser)

    response = admin_security_events(request)

    assert response.status_code == 200
    assert response.data['total'] == 1
    assert response.data['events'][0]['severity'] == 'HIGH'


def test_content_moderator_cannot_view_security_events(content_moderator, unresolved_event):
    """Matches master's own role_permissions: security events are
    super_admin-only, granted to none of the other 3 roles."""
    request = factory.get('/admin/security-events/')
    force_authenticate(request, user=content_moderator)

    response = admin_security_events(request)

    assert response.status_code == 403


def test_admin_resolve_security_event(superuser, unresolved_event):
    request = factory.post(f'/admin/security-events/{unresolved_event.id}/resolve/')
    force_authenticate(request, user=superuser)

    response = admin_resolve_security_event(request, event_id=unresolved_event.id)

    assert response.status_code == 200, response.data
    unresolved_event.refresh_from_db()
    assert unresolved_event.is_resolved is True


def test_admin_resolve_security_event_404_for_unknown_id(superuser, db):
    request = factory.post('/admin/security-events/999999/resolve/')
    force_authenticate(request, user=superuser)

    response = admin_resolve_security_event(request, event_id=999999)

    assert response.status_code == 404


def test_content_moderator_cannot_resolve_security_event(content_moderator, unresolved_event):
    request = factory.post(f'/admin/security-events/{unresolved_event.id}/resolve/')
    force_authenticate(request, user=content_moderator)

    response = admin_resolve_security_event(request, event_id=unresolved_event.id)

    assert response.status_code == 403
    unresolved_event.refresh_from_db()
    assert unresolved_event.is_resolved is False


def test_admin_mark_all_security_events_read(superuser, unresolved_event):
    SecurityEvent.objects.create(event_type='PERMISSION_DENIED', severity='HIGH', username='u', endpoint='/x', is_resolved=False)

    request = factory.post('/admin/security-events/mark-all-read/')
    force_authenticate(request, user=superuser)

    response = admin_mark_all_security_events_read(request)

    assert response.status_code == 200
    assert SecurityEvent.objects.filter(is_resolved=False).count() == 0


def test_admin_security_stats_counts_events(superuser, unresolved_event):
    request = factory.get('/admin/security-stats/')
    force_authenticate(request, user=superuser)

    response = admin_security_stats(request)

    assert response.status_code == 200
    assert response.data['unresolved_count'] == 1
    assert response.data['recent_events'] == 1


def test_admin_log_security_event_creates_row(superuser):
    request = factory.post('/admin/security-events/log/', {
        'event_type': 'SUSPICIOUS_ACTIVITY', 'severity': 'HIGH', 'page': '/settings', 'details': 'tampered request',
    }, format='json')
    force_authenticate(request, user=superuser)

    response = admin_log_security_event(request)

    assert response.status_code == 200, response.data
    event = SecurityEvent.objects.get(event_type='SUSPICIOUS_ACTIVITY', page='/settings')
    assert event.user == superuser
    assert event.severity == 'HIGH'


def test_admin_log_security_event_requires_event_type(superuser, db):
    request = factory.post('/admin/security-events/log/', {}, format='json')
    force_authenticate(request, user=superuser)

    response = admin_log_security_event(request)

    assert response.status_code == 400
