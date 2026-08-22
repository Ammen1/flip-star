"""Tests for common/security/client_ip.py."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from common.security.client_ip import get_client_ip

pytestmark = pytest.mark.unit

factory = RequestFactory()


def _request(remote_addr: str, xff: str | None = None):
    extra = {'REMOTE_ADDR': remote_addr}
    if xff is not None:
        extra['HTTP_X_FORWARDED_FOR'] = xff
    return factory.get('/', **extra)


def test_no_trusted_proxies_configured_ignores_xff(settings):
    settings.TRUSTED_PROXY_IPS = []
    request = _request('203.0.113.9', xff='1.2.3.4')

    assert get_client_ip(request) == '203.0.113.9'


def test_untrusted_direct_peer_has_xff_ignored(settings):
    """An attacker connecting directly and setting X-Forwarded-For themselves
    must not be able to make the server believe they are some other IP."""
    settings.TRUSTED_PROXY_IPS = ['10.0.0.1']
    request = _request('203.0.113.9', xff='1.2.3.4')

    assert get_client_ip(request) == '203.0.113.9'


def test_trusted_proxy_xff_is_honored(settings):
    settings.TRUSTED_PROXY_IPS = ['127.0.0.1']
    request = _request('127.0.0.1', xff='198.51.100.7')

    assert get_client_ip(request) == '198.51.100.7'


def test_trusted_proxy_chain_skips_trusted_hops(settings):
    """Multiple proxy hops: walk from the right, skip entries that are
    themselves trusted proxies, return the first untrusted (real client) hop."""
    settings.TRUSTED_PROXY_IPS = ['127.0.0.1', '10.0.0.5']
    request = _request('127.0.0.1', xff='198.51.100.7, 10.0.0.5')

    assert get_client_ip(request) == '198.51.100.7'


def test_trusted_proxy_with_no_xff_header_falls_back_to_remote_addr(settings):
    settings.TRUSTED_PROXY_IPS = ['127.0.0.1']
    request = _request('127.0.0.1', xff=None)

    assert get_client_ip(request) == '127.0.0.1'


def test_cidr_range_is_honored(settings):
    settings.TRUSTED_PROXY_IPS = ['10.0.0.0/24']
    request = _request('10.0.0.42', xff='198.51.100.7')

    assert get_client_ip(request) == '198.51.100.7'


def test_malformed_xff_entry_does_not_crash(settings):
    settings.TRUSTED_PROXY_IPS = ['127.0.0.1']
    request = _request('127.0.0.1', xff='not-an-ip')

    # Not a valid IP, so treated as untrusted -- returned as-is rather than
    # raising. Callers (throttling, logging) just get an opaque string key.
    assert get_client_ip(request) == 'not-an-ip'


def test_malformed_trusted_proxy_setting_is_ignored(settings):
    settings.TRUSTED_PROXY_IPS = ['not-a-valid-network', '127.0.0.1']
    request = _request('127.0.0.1', xff='198.51.100.7')

    assert get_client_ip(request) == '198.51.100.7'
