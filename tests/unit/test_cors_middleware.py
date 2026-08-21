"""
Regression tests for the CORS wildcard+credentials fix (audit finding M-10).

Before the fix, an unknown origin got Access-Control-Allow-Origin: * AND
Access-Control-Allow-Credentials: true on the same response -- a pairing
browsers reject, but that a non-browser HTTP client would happily honour,
amounting to a credentialed cross-origin allowlist of "everyone." These
tests exist specifically to catch a regression back to that behavior.
"""

from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from common.middleware.cors import PermissiveCorsMiddleware

pytestmark = pytest.mark.unit

factory = RequestFactory()


@pytest.fixture(autouse=True)
def _allowed_origins(settings):
    settings.CORS_ALLOWED_ORIGINS = ['https://flipstar.et']


class TestPermissiveCorsMiddleware:
    def setup_method(self):
        self.mw = PermissiveCorsMiddleware(get_response=lambda r: None)

    def test_trusted_origin_gets_credentialed_headers(self):
        request = factory.get('/api/posts/', HTTP_ORIGIN='https://flipstar.et')
        response = self.mw.process_response(request, HttpResponse())

        assert response['Access-Control-Allow-Origin'] == 'https://flipstar.et'
        assert response['Access-Control-Allow-Credentials'] == 'true'

    def test_untrusted_origin_gets_no_cors_headers_at_all(self):
        request = factory.get('/api/posts/', HTTP_ORIGIN='https://evil.example.com')
        response = self.mw.process_response(request, HttpResponse())

        assert 'Access-Control-Allow-Origin' not in response
        assert 'Access-Control-Allow-Credentials' not in response

    def test_never_pairs_wildcard_origin_with_credentials(self):
        request = factory.get('/api/posts/', HTTP_ORIGIN='https://evil.example.com')
        response = self.mw.process_response(request, HttpResponse())

        assert response.get('Access-Control-Allow-Origin') != '*'

    def test_missing_origin_header_gets_no_cors_headers(self):
        request = factory.get('/api/posts/')
        response = self.mw.process_response(request, HttpResponse())

        assert 'Access-Control-Allow-Origin' not in response

    def test_preflight_from_trusted_origin_gets_max_age(self):
        request = factory.options('/api/posts/', HTTP_ORIGIN='https://flipstar.et')
        response = self.mw.process_request(request)

        assert response['Access-Control-Max-Age'] == '86400'
        assert response['Access-Control-Allow-Origin'] == 'https://flipstar.et'

    def test_preflight_from_untrusted_origin_gets_no_max_age_or_headers(self):
        request = factory.options('/api/posts/', HTTP_ORIGIN='https://evil.example.com')
        response = self.mw.process_request(request)

        assert 'Access-Control-Max-Age' not in response
        assert 'Access-Control-Allow-Origin' not in response
