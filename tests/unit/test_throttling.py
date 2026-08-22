"""Tests for common/throttling.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from common.throttling import (
    LoginAnonThrottle,
    _get_throttle_ident,
    check_and_increment_failure,
    clear_failures,
    is_blocked,
    reset_throttle,
)

pytestmark = pytest.mark.unit

factory = RequestFactory()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _anon_request(remote_addr='203.0.113.5', xff=None, data=None):
    extra = {'REMOTE_ADDR': remote_addr}
    if xff is not None:
        extra['HTTP_X_FORWARDED_FOR'] = xff
    request = factory.post('/', **extra)
    request.user = None
    request.data = data or {}
    return request


# ---------------------------------------------------------------------------
# _ExtendedRateMixin.parse_rate -- the N/Mperiod format DRF's own parser
# raises KeyError on.
# ---------------------------------------------------------------------------

def test_extended_rate_format_is_parsed():
    throttle = LoginAnonThrottle()
    assert throttle.parse_rate('6/10min') == (6, 600)


def test_standard_rate_format_still_works():
    throttle = LoginAnonThrottle()
    assert throttle.parse_rate('5/min') == (5, 60)


def test_none_rate_is_passed_through():
    throttle = LoginAnonThrottle()
    assert throttle.parse_rate(None) == (None, None)


# ---------------------------------------------------------------------------
# _get_throttle_ident -- account identity first, IP last, never spoofable
# ---------------------------------------------------------------------------

def test_authenticated_user_is_identified_by_id():
    request = _anon_request()
    request.user = MagicMock(is_authenticated=True, id=42)

    assert _get_throttle_ident(request) == 'user_42'


def test_anonymous_request_uses_body_identifier_over_ip():
    request = _anon_request(data={'username': 'alice'})

    assert _get_throttle_ident(request) == 'username_alice'


def test_anonymous_request_with_no_identifier_falls_back_to_ip():
    request = _anon_request(remote_addr='203.0.113.5')

    assert _get_throttle_ident(request) == 'ip_203.0.113.5'


def test_ip_fallback_ignores_spoofed_x_forwarded_for(settings):
    """The whole point of this fix: an attacker who is not behind a
    trusted proxy cannot change their throttle identity by lying about
    X-Forwarded-For, which would otherwise let them dodge a block by
    claiming a fresh IP on every request."""
    settings.TRUSTED_PROXY_IPS = []  # nothing trusted -> XFF always ignored

    real_attacker_ip = '203.0.113.5'
    first = _anon_request(remote_addr=real_attacker_ip, xff='1.1.1.1')
    second = _anon_request(remote_addr=real_attacker_ip, xff='2.2.2.2')

    assert _get_throttle_ident(first) == _get_throttle_ident(second) == f'ip_{real_attacker_ip}'


def test_spoofed_xff_from_an_untrusted_peer_cannot_bypass_a_block(settings):
    """End-to-end version of the identity test: block the real IP, then
    confirm a request claiming a different X-Forwarded-For every time is
    still recognised as blocked."""
    settings.TRUSTED_PROXY_IPS = []
    real_attacker_ip = '203.0.113.5'

    for _ in range(3):
        check_and_increment_failure(
            _anon_request(remote_addr=real_attacker_ip, xff='1.1.1.1'), 'login', 3, 600,
        )
    assert is_blocked(_anon_request(remote_addr=real_attacker_ip), 'login', 3)

    # Same attacker, new spoofed header on every attempt -- still blocked,
    # because the identifier never depended on the header in the first place.
    spoofed = _anon_request(remote_addr=real_attacker_ip, xff='9.9.9.9')
    assert is_blocked(spoofed, 'login', 3)


# ---------------------------------------------------------------------------
# is_blocked / check_and_increment_failure / clear_failures / reset_throttle
# ---------------------------------------------------------------------------

def test_not_blocked_before_any_failures():
    request = _anon_request()
    assert is_blocked(request, 'login', 6) is False


def test_becomes_blocked_after_max_attempts():
    request = _anon_request()
    for _ in range(6):
        check_and_increment_failure(request, 'login', 6, 600)

    assert is_blocked(request, 'login', 6) is True


def test_remaining_count_decreases_and_floors_at_zero():
    request = _anon_request()
    results = [check_and_increment_failure(request, 'login', 3, 600) for _ in range(5)]

    assert results == [2, 1, 0, 0, 0]


def test_clear_failures_unblocks():
    request = _anon_request()
    for _ in range(6):
        check_and_increment_failure(request, 'login', 6, 600)
    assert is_blocked(request, 'login', 6) is True

    clear_failures(request, 'login')

    assert is_blocked(request, 'login', 6) is False


def test_different_scopes_do_not_share_a_counter():
    request = _anon_request()
    for _ in range(6):
        check_and_increment_failure(request, 'login', 6, 600)

    assert is_blocked(request, 'login', 6) is True
    assert is_blocked(request, 'password_reset', 6) is False


def test_reset_throttle_clears_the_drf_rate_limit_cache_key():
    request = _anon_request()
    ident = _get_throttle_ident(request)
    cache.set(f'throttle_login_{ident}', [1, 2, 3], 600)

    reset_throttle(request, 'login')

    assert cache.get(f'throttle_login_{ident}') is None
