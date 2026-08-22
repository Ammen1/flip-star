"""
Regression tests proving common/middleware/security.py actually persists a
SecurityEvent row at each of its logger.warning() call sites -- ported from
master's SecurityEvent model (api/models.py there), which common/middleware/
security.py's own docstring had explicitly deferred pending the model
landing (see that docstring's history). tests/unit/test_security_middleware.py
covers the response-shape behavior without a database; this file covers the
DB write those same call sites now also perform.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from api.models.admin import SecurityEvent
from common.middleware.security import AdminPathGuardMiddleware, SecurityScanMiddleware

pytestmark = pytest.mark.integration

factory = RequestFactory()


def test_admin_path_guard_logs_unauthorized_api_event_for_anonymous(db):
    mw = AdminPathGuardMiddleware(get_response=lambda r: None)
    request = factory.get('/api/v1/admin/users/')

    response = mw.process_request(request)

    assert response.status_code == 401
    event = SecurityEvent.objects.get(endpoint='/api/v1/admin/users/', event_type='UNAUTHORIZED_API')
    assert event.severity == 'HIGH'
    assert event.username == 'Anonymous'
    assert event.user is None
    assert event.details == 'Authentication required'


def test_admin_path_guard_logs_unauthorized_api_event_for_non_staff(db, django_user_model):
    user = django_user_model.objects.create_user(username='sec_event_nonstaff', password='x')
    try:
        mw = AdminPathGuardMiddleware(get_response=lambda r: None)
        request = factory.get('/api/v1/admin/users/')
        request.user = user

        response = mw.process_request(request)

        assert response.status_code == 403
        event = SecurityEvent.objects.get(endpoint='/api/v1/admin/users/', details='Admin privileges required')
        assert event.severity == 'HIGH'
        assert event.user == user
        assert event.username == 'sec_event_nonstaff'
    finally:
        user.delete()


def test_admin_path_guard_logs_permission_denied_for_read_only_role_write(db, django_user_model):
    from api.models.subscription import AdminRole

    user = django_user_model.objects.create_user(username='sec_event_readonly', password='x', is_staff=True)
    AdminRole.objects.create(user=user, role='support_agent', permission_level='read_only')
    try:
        mw = AdminPathGuardMiddleware(get_response=lambda r: None)
        request = factory.post('/api/v1/admin/users/')
        request.user = user

        response = mw.process_request(request)

        assert response.status_code == 403
        event = SecurityEvent.objects.filter(endpoint='/api/v1/admin/users/', event_type='PERMISSION_DENIED').first()
        assert event is not None
        assert event.severity == 'MEDIUM'
        assert 'level=read_only' in event.details
    finally:
        user.delete()


def test_security_scan_logs_scanner_probe_event_for_blocked_path(db):
    mw = SecurityScanMiddleware(get_response=lambda r: None)
    request = factory.get('/.env')
    request.user = MagicMock(is_authenticated=False)

    response = mw.process_request(request)

    assert response.status_code == 403
    event = SecurityEvent.objects.get(event_type='SCANNER_PROBE', endpoint='/.env')
    assert event.severity == 'LOW'
    assert event.username == 'Anonymous'


def test_security_scan_logs_scanner_probe_event_for_suspicious_root_probe(db):
    mw = SecurityScanMiddleware(get_response=lambda r: None)
    request = factory.get('/', HTTP_USER_AGENT='sqlmap/1.0')
    request.user = MagicMock(is_authenticated=False)

    response = mw.process_request(request)

    assert response.status_code == 403
    event = SecurityEvent.objects.get(event_type='SCANNER_PROBE', endpoint='/')
    assert 'suspicious user agent' in event.details


def test_security_event_write_failure_does_not_break_the_response(db):
    """_log_security_event must swallow its own failures -- a broken audit
    log must never be the reason a real security block stops working."""
    mw = SecurityScanMiddleware(get_response=lambda r: None)
    request = factory.get('/.env')
    request.user = MagicMock(is_authenticated=False)

    with patch('api.models.admin.SecurityEvent.objects.create', side_effect=RuntimeError('db down')):
        response = mw.process_request(request)

    assert response.status_code == 403
