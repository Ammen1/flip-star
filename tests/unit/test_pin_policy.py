"""
Tests for common/security/pin_policy.py and its use at every PIN-creation and
PIN-change entry point.

No database is available in this suite (see tests/conftest.py). Every view
tested here places the weak-PIN check before any ORM call, so calling the
view directly through APIRequestFactory and asserting a 400 exercises the
real guard without needing a database -- if any of these regressed to check
the PIN *after* a DB read, the test would start erroring instead of failing
cleanly, which is itself a useful signal.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.core.cache import cache
from rest_framework import serializers
from rest_framework.test import APIRequestFactory, force_authenticate

from api.serializers.core import RegisterSerializer
from api.views.core import (
    change_password,
    forgot_password_confirm,
    forgot_password_phone_verify,
    login_with_subscription_otp,
    register_with_phone,
    reset_password,
)
from common.security.pin_policy import EXPLICIT_BLOCKLIST, is_pin_too_weak

pytestmark = pytest.mark.unit

factory = APIRequestFactory()


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """
    Several of these endpoints now share the 'password_reset' throttle scope
    (see common/throttling.py) and this suite reuses the same email/phone
    across tests, so without a clean cache each test's requests count toward
    the next test's rate limit -- a real 429 masquerading as a test failure.
    """
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# is_pin_too_weak()
# ---------------------------------------------------------------------------

def test_valid_pin_is_accepted():
    too_weak, reason = is_pin_too_weak('307942')
    assert too_weak is False
    assert reason == ''


def test_all_same_digit_rejected():
    too_weak, reason = is_pin_too_weak('222222')
    assert too_weak is True
    assert 'same digit' in reason


def test_ascending_sequential_rejected():
    too_weak, reason = is_pin_too_weak('234567')
    assert too_weak is True
    assert 'sequential' in reason


def test_descending_sequential_rejected():
    too_weak, reason = is_pin_too_weak('765432')
    assert too_weak is True
    assert 'sequential' in reason


def test_palindrome_rejected():
    too_weak, reason = is_pin_too_weak('374473')
    assert too_weak is True
    assert 'palindrome' in reason


def test_blocklisted_pin_rejected():
    too_weak, reason = is_pin_too_weak('123456')
    assert too_weak is True
    assert 'common' in reason


@pytest.mark.parametrize('pin', sorted(EXPLICIT_BLOCKLIST))
def test_every_blocklist_entry_is_rejected(pin):
    too_weak, _ = is_pin_too_weak(pin)
    assert too_weak is True


@pytest.mark.parametrize('pin', ['', '12345', '1234567', 'abcdef', '12345a', None])
def test_malformed_pin_rejected(pin):
    too_weak, reason = is_pin_too_weak(pin)
    assert too_weak is True
    assert 'exactly 6 digits' in reason


# ---------------------------------------------------------------------------
# Registration (RegisterSerializer.validate_password)
# ---------------------------------------------------------------------------

def test_register_serializer_rejects_weak_password():
    serializer = RegisterSerializer()
    with pytest.raises(serializers.ValidationError):
        serializer.validate_password('111111')


def test_register_serializer_accepts_strong_password():
    serializer = RegisterSerializer()
    assert serializer.validate_password('307942') == '307942'


# ---------------------------------------------------------------------------
# Endpoints -- each must reject a weak PIN with 400 before touching the DB.
# ---------------------------------------------------------------------------

def test_reset_password_rejects_weak_pin():
    request = factory.post('/x', {'email': 'a@example.com', 'new_password': '111111'}, format='json')
    response = reset_password(request)
    assert response.status_code == 400
    assert 'error' in response.data


def test_reset_password_rejects_malformed_pin():
    request = factory.post('/x', {'email': 'a@example.com', 'new_password': 'abcdef'}, format='json')
    response = reset_password(request)
    assert response.status_code == 400


def test_forgot_password_confirm_rejects_weak_pin():
    request = factory.post(
        '/x', {'email': 'a@example.com', 'code': '123456', 'new_password': '000000'}, format='json',
    )
    response = forgot_password_confirm(request)
    assert response.status_code == 400


def test_forgot_password_phone_verify_rejects_weak_pin():
    request = factory.post(
        '/x', {'phone': '0911223344', 'code': '1234', 'new_password': '123321'}, format='json',
    )
    response = forgot_password_phone_verify(request)
    assert response.status_code == 400


def test_register_with_phone_rejects_weak_pin():
    request = factory.post(
        '/x', {'phone': '0911223344', 'username': 'someone', 'password': '654321'}, format='json',
    )
    response = register_with_phone(request)
    assert response.status_code == 400


def test_login_with_subscription_otp_rejects_weak_pin():
    request = factory.post(
        '/x', {'phone': '0911223344', 'otp': '1234', 'password': '111111'}, format='json',
    )
    response = login_with_subscription_otp(request)
    assert response.status_code == 400


def test_change_password_rejects_weak_pin():
    """change_password requires IsAuthenticated, so force_authenticate stands
    in for a real logged-in user -- a MagicMock is enough because the weak-PIN
    check runs before request.user is used for anything else."""
    request = factory.post(
        '/x', {'current_password': 'whatever1', 'new_password': '111111'}, format='json',
    )
    force_authenticate(request, user=MagicMock(is_authenticated=True))

    response = change_password(request)

    assert response.status_code == 400
    assert 'error' in response.data
