"""
Tests for common/authentication/tokens.py.

No database is available in this suite (see tests/conftest.py), so these
mock the token DRF's TokenAuthentication would normally look up, rather than
creating a real User/Token pair. What's under test is exactly the TTL
decision -- reject-and-delete past the cutoff, pass through under it -- not
DRF's own credential lookup, which is untouched here.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from common.authentication import ExpiringTokenAuthentication

pytestmark = pytest.mark.unit

_LOOKUP = 'rest_framework.authentication.TokenAuthentication.authenticate_credentials'


def _token(age_days):
    token = MagicMock()
    token.created = timezone.now() - timedelta(days=age_days)
    return token


def test_fresh_token_authenticates(settings):
    settings.AUTH_TOKEN_TTL_DAYS = 14
    user, token = MagicMock(), _token(age_days=1)
    auth = ExpiringTokenAuthentication()

    with patch(_LOOKUP, return_value=(user, token)):
        result_user, result_token = auth.authenticate_credentials('key')

    assert result_user is user
    assert result_token is token
    token.delete.assert_not_called()


def test_expired_token_is_rejected_and_deleted(settings):
    settings.AUTH_TOKEN_TTL_DAYS = 14
    user, token = MagicMock(), _token(age_days=15)
    auth = ExpiringTokenAuthentication()

    with patch(_LOOKUP, return_value=(user, token)):
        with pytest.raises(AuthenticationFailed, match='expired'):
            auth.authenticate_credentials('key')

    token.delete.assert_called_once()


def test_token_just_inside_ttl_is_accepted(settings):
    settings.AUTH_TOKEN_TTL_DAYS = 14
    user, token = MagicMock(), _token(age_days=13)
    auth = ExpiringTokenAuthentication()

    with patch(_LOOKUP, return_value=(user, token)):
        # Must not raise.
        auth.authenticate_credentials('key')

    token.delete.assert_not_called()


def test_token_just_past_ttl_is_rejected(settings):
    settings.AUTH_TOKEN_TTL_DAYS = 14
    user, token = MagicMock(), _token(age_days=14.01)
    auth = ExpiringTokenAuthentication()

    with patch(_LOOKUP, return_value=(user, token)):
        with pytest.raises(AuthenticationFailed):
            auth.authenticate_credentials('key')


@pytest.mark.parametrize('ttl', [0, None])
def test_ttl_disabled_never_expires(settings, ttl):
    settings.AUTH_TOKEN_TTL_DAYS = ttl
    user, token = MagicMock(), _token(age_days=9999)
    auth = ExpiringTokenAuthentication()

    with patch(_LOOKUP, return_value=(user, token)):
        # Must not raise even for a token that's years old.
        auth.authenticate_credentials('key')

    token.delete.assert_not_called()


def test_error_message_does_not_leak_the_token_value(settings):
    settings.AUTH_TOKEN_TTL_DAYS = 14
    user, token = MagicMock(), _token(age_days=15)
    auth = ExpiringTokenAuthentication()
    secret_key = 'super-secret-token-value-should-never-appear-in-errors'

    with patch(_LOOKUP, return_value=(user, token)):
        with pytest.raises(AuthenticationFailed) as excinfo:
            auth.authenticate_credentials(secret_key)

    assert secret_key not in str(excinfo.value)
