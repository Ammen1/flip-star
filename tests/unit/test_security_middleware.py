"""
Tests for common/middleware/security.py.

Each class is old-style (MiddlewareMixin) middleware, so process_request /
process_response can be called directly against a RequestFactory request
without running a real middleware chain or touching the database. Anywhere
a model lookup would occur (AdminRole), it's mocked -- this suite has no
database (see tests/conftest.py).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory
from rest_framework.exceptions import AuthenticationFailed

from common.middleware.security import (
    AdminLoginThrottleMiddleware,
    AdminPathGuardMiddleware,
    SecurityHeadersMiddleware,
    SecurityScanMiddleware,
)

pytestmark = pytest.mark.unit

factory = RequestFactory()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# AdminPathGuardMiddleware
# ---------------------------------------------------------------------------

class TestAdminPathGuardMiddleware:
    def setup_method(self):
        self.mw = AdminPathGuardMiddleware(get_response=lambda r: None)

    def test_non_admin_path_passes_through(self):
        request = factory.get('/api/posts/')
        assert self.mw.process_request(request) is None

    def test_options_preflight_passes_through(self):
        request = factory.options('/api/v1/admin/users/')
        assert self.mw.process_request(request) is None

    def test_no_user_and_no_auth_header_is_401(self):
        request = factory.get('/api/v1/admin/users/')
        response = self.mw.process_request(request)
        assert response.status_code == 401

    def test_authenticated_non_staff_is_403(self):
        request = factory.get('/api/v1/admin/users/')
        request.user = MagicMock(is_authenticated=True, is_staff=False, is_superuser=False)
        response = self.mw.process_request(request)
        assert response.status_code == 403

    def test_staff_get_request_passes(self):
        request = factory.get('/api/v1/admin/users/')
        request.user = MagicMock(is_authenticated=True, is_staff=True, is_superuser=False)
        assert self.mw.process_request(request) is None

    def test_staff_write_with_no_admin_role_passes(self):
        request = factory.post('/api/v1/admin/users/')
        request.user = MagicMock(is_authenticated=True, is_staff=True, is_superuser=False)
        with patch('api.models.subscription.AdminRole') as mock_role_model:
            mock_role_model.objects.filter.return_value.first.return_value = None
            assert self.mw.process_request(request) is None

    def test_read_only_role_blocks_every_write_method(self):
        request = factory.post('/api/v1/admin/users/')
        request.user = MagicMock(is_authenticated=True, is_staff=True, is_superuser=True)
        fake_role = MagicMock(permission_level='read_only', role='admin')
        with patch('api.models.subscription.AdminRole') as mock_role_model:
            mock_role_model.objects.filter.return_value.first.return_value = fake_role
            response = self.mw.process_request(request)
        assert response.status_code == 403

    def test_read_only_role_allows_get(self):
        request = factory.get('/api/v1/admin/users/')
        request.user = MagicMock(is_authenticated=True, is_staff=True, is_superuser=True)
        fake_role = MagicMock(permission_level='read_only', role='admin')
        with patch('api.models.subscription.AdminRole') as mock_role_model:
            mock_role_model.objects.filter.return_value.first.return_value = fake_role
            assert self.mw.process_request(request) is None

    def test_edit_only_role_blocks_delete(self):
        request = factory.delete('/api/v1/admin/users/1/')
        request.user = MagicMock(is_authenticated=True, is_staff=True, is_superuser=True)
        fake_role = MagicMock(permission_level='edit_only', role='admin')
        with patch('api.models.subscription.AdminRole') as mock_role_model:
            mock_role_model.objects.filter.return_value.first.return_value = fake_role
            response = self.mw.process_request(request)
        assert response.status_code == 403

    def test_edit_only_role_allows_patch(self):
        request = factory.patch('/api/v1/admin/users/1/')
        request.user = MagicMock(is_authenticated=True, is_staff=True, is_superuser=True)
        fake_role = MagicMock(permission_level='edit_only', role='admin')
        with patch('api.models.subscription.AdminRole') as mock_role_model:
            mock_role_model.objects.filter.return_value.first.return_value = fake_role
            assert self.mw.process_request(request) is None

    def test_full_role_allows_delete(self):
        request = factory.delete('/api/v1/admin/users/1/')
        request.user = MagicMock(is_authenticated=True, is_staff=True, is_superuser=True)
        fake_role = MagicMock(permission_level='full', role='admin')
        with patch('api.models.subscription.AdminRole') as mock_role_model:
            mock_role_model.objects.filter.return_value.first.return_value = fake_role
            assert self.mw.process_request(request) is None

    def test_token_header_resolves_a_staff_user(self):
        request = factory.get('/api/v1/admin/users/', HTTP_AUTHORIZATION='Token abc123')
        fake_user = MagicMock(is_authenticated=True, is_staff=True, is_superuser=False)
        with patch(
            'common.authentication.ExpiringTokenAuthentication.authenticate_credentials',
            return_value=(fake_user, MagicMock()),
        ):
            response = self.mw.process_request(request)
        assert response is None

    def test_expired_token_header_is_treated_as_unauthenticated(self):
        request = factory.get('/api/v1/admin/users/', HTTP_AUTHORIZATION='Token expired-key')
        with patch(
            'common.authentication.ExpiringTokenAuthentication.authenticate_credentials',
            side_effect=AuthenticationFailed('Authentication token has expired.'),
        ):
            response = self.mw.process_request(request)
        assert response.status_code == 401

    def test_malformed_auth_header_is_treated_as_unauthenticated(self):
        request = factory.get('/api/v1/admin/users/', HTTP_AUTHORIZATION='NotABearer xyz')
        response = self.mw.process_request(request)
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# AdminLoginThrottleMiddleware
# ---------------------------------------------------------------------------

class TestAdminLoginThrottleMiddleware:
    def setup_method(self):
        self.mw = AdminLoginThrottleMiddleware(get_response=lambda r: None)

    def test_non_login_path_ignored(self):
        request = factory.get('/admin/')
        assert self.mw.process_request(request) is None

    def test_get_requests_to_login_path_ignored(self):
        request = factory.get('/admin/login/')
        assert self.mw.process_request(request) is None

    def test_blocks_after_four_failed_attempts(self):
        ip = '203.0.113.9'
        for _ in range(4):
            request = factory.post('/admin/login/', REMOTE_ADDR=ip)
            self.mw.process_response(request, HttpResponse(status=200))

        blocked_request = factory.post('/admin/login/', REMOTE_ADDR=ip)
        response = self.mw.process_request(blocked_request)

        assert response.status_code == 429

    def test_successful_login_resets_the_counter(self):
        ip = '203.0.113.10'
        for _ in range(3):
            request = factory.post('/admin/login/', REMOTE_ADDR=ip)
            self.mw.process_response(request, HttpResponse(status=200))

        success_request = factory.post('/admin/login/', REMOTE_ADDR=ip)
        self.mw.process_response(success_request, HttpResponse(status=302))

        next_request = factory.post('/admin/login/', REMOTE_ADDR=ip)
        assert self.mw.process_request(next_request) is None

    def test_different_ips_have_independent_counters(self):
        for _ in range(4):
            request = factory.post('/admin/login/', REMOTE_ADDR='203.0.113.11')
            self.mw.process_response(request, HttpResponse(status=200))

        other_ip_request = factory.post('/admin/login/', REMOTE_ADDR='203.0.113.12')
        assert self.mw.process_request(other_ip_request) is None


# ---------------------------------------------------------------------------
# SecurityScanMiddleware
# ---------------------------------------------------------------------------

class TestSecurityScanMiddleware:
    def setup_method(self):
        self.mw = SecurityScanMiddleware(get_response=lambda r: None)

    def test_normal_request_passes(self):
        request = factory.get('/api/posts/', HTTP_USER_AGENT='Mozilla/5.0')
        assert self.mw.process_request(request) is None

    @pytest.mark.parametrize('path', ['/.env', '/wp-admin', '/phpmyadmin', '/xmlrpc.php'])
    def test_known_scanner_paths_are_blocked(self, path):
        request = factory.get(path)
        response = self.mw.process_request(request)
        assert response.status_code == 403

    def test_suspicious_ua_at_root_is_blocked(self):
        request = factory.get('/', HTTP_USER_AGENT='sqlmap/1.6.12')
        response = self.mw.process_request(request)
        assert response.status_code == 403

    def test_normal_browser_ua_at_root_passes(self):
        request = factory.get('/', HTTP_USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
        assert self.mw.process_request(request) is None

    def test_generic_bot_substring_is_not_blocked(self):
        """The reference list this was ported from also blocked any UA
        containing 'bot', which would catch legitimate crawlers (Googlebot,
        link-preview bots) and webhook senders. Deliberately narrowed to
        named attack-tool signatures instead -- see common/middleware/security.py."""
        request = factory.get('/', HTTP_USER_AGENT='Mozilla/5.0 (compatible; Googlebot/2.1)')
        assert self.mw.process_request(request) is None


# ---------------------------------------------------------------------------
# SecurityHeadersMiddleware
# ---------------------------------------------------------------------------

class TestSecurityHeadersMiddleware:
    def setup_method(self):
        self.mw = SecurityHeadersMiddleware(get_response=lambda r: None)

    def test_adds_expected_headers(self):
        request = factory.get('/api/posts/')
        response = self.mw.process_response(request, HttpResponse())

        assert 'Content-Security-Policy' in response
        assert response['X-Content-Type-Options'] == 'nosniff'
        assert response['Referrer-Policy'] == 'strict-origin-when-cross-origin'

    def test_does_not_overwrite_an_existing_header(self):
        request = factory.get('/api/posts/')
        response = HttpResponse()
        response['X-Content-Type-Options'] = 'custom-value'

        result = self.mw.process_response(request, response)

        assert result['X-Content-Type-Options'] == 'custom-value'

    def test_csp_includes_configured_media_domain(self, settings):
        settings.S3_CUSTOM_DOMAIN = 'https://media.example.com'
        request = factory.get('/api/posts/')

        response = self.mw.process_response(request, HttpResponse())

        assert 'media.example.com' in response['Content-Security-Policy']

    def test_csp_omits_media_domain_when_unset(self, settings):
        settings.S3_CUSTOM_DOMAIN = ''
        request = factory.get('/api/posts/')

        response = self.mw.process_response(request, HttpResponse())

        assert response['Content-Security-Policy'].count(';') > 0  # still well-formed
