"""
Regression tests for query_mandate_from_telebirr (api/views/direct_debit.py)
-- ported from the master branch, missing entirely in the current project
before this change. An ops/support diagnostic that queries a payer phone
number's Direct Debit mandate status directly from Telebirr via
telebirr_direct_debit_service.query_mandate_by_payer (already present,
ported earlier this session as part of the direct-debit flow).

Master gates this behind bare IsAuthenticated with an arbitrary
payer_msisdn query param -- any logged-in user could probe any phone
number's mandate status. Ported behind HasAdminPermission('view_payments')
instead, matching this session's established pattern of tightening
under-scoped master endpoints rather than copying them as-is.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views.direct_debit import query_mandate_from_telebirr

pytestmark = pytest.mark.integration

factory = APIRequestFactory()


@pytest.fixture
def superuser(db):
    u = User.objects.create_superuser(username='mandate_query_super', password='x', email='s@example.com')
    yield u
    u.delete()


@pytest.fixture
def plain_user(db):
    u = User.objects.create_user(username='mandate_query_plain', password='x')
    yield u
    u.delete()


def test_query_mandate_from_telebirr_returns_result_for_admin(superuser):
    fake_result = {
        'success': True, 'message': 'OK', 'response_code': '00',
        'conversation_id': 'conv-1', 'response_text': '<xml/>',
    }
    with patch(
        'api.views.direct_debit.telebirr_direct_debit_service.query_mandate_by_payer',
        return_value=fake_result,
    ) as mock_query:
        request = factory.get('/admin/direct-debit/query-mandate/?payer_msisdn=251911223344')
        force_authenticate(request, user=superuser)

        response = query_mandate_from_telebirr(request)

    assert response.status_code == 200, response.data
    assert response.data['success'] is True
    assert response.data['conversation_id'] == 'conv-1'
    mock_query.assert_called_once_with(payer_msisdn='251911223344', mandate_statuses=None, debug=True)


def test_query_mandate_from_telebirr_parses_comma_separated_statuses(superuser):
    with patch(
        'api.views.direct_debit.telebirr_direct_debit_service.query_mandate_by_payer',
        return_value={'success': True},
    ) as mock_query:
        request = factory.get('/admin/direct-debit/query-mandate/?payer_msisdn=251911223344&mandate_statuses=03,01')
        force_authenticate(request, user=superuser)

        query_mandate_from_telebirr(request)

    mock_query.assert_called_once_with(payer_msisdn='251911223344', mandate_statuses=['03', '01'], debug=True)


def test_query_mandate_from_telebirr_rejects_missing_payer_msisdn(superuser):
    request = factory.get('/admin/direct-debit/query-mandate/')
    force_authenticate(request, user=superuser)

    response = query_mandate_from_telebirr(request)

    assert response.status_code == 400


def test_query_mandate_from_telebirr_returns_400_on_service_failure(superuser):
    with patch(
        'api.views.direct_debit.telebirr_direct_debit_service.query_mandate_by_payer',
        return_value={'success': False, 'error': 'Telebirr rejected the request'},
    ):
        request = factory.get('/admin/direct-debit/query-mandate/?payer_msisdn=251911223344')
        force_authenticate(request, user=superuser)

        response = query_mandate_from_telebirr(request)

    assert response.status_code == 400
    assert response.data['error'] == 'Telebirr rejected the request'


def test_query_mandate_from_telebirr_rejects_non_admin_user(plain_user):
    """A plain authenticated user must not be able to probe an arbitrary
    phone number's mandate status -- unlike master's bare IsAuthenticated."""
    request = factory.get('/admin/direct-debit/query-mandate/?payer_msisdn=251911223344')
    force_authenticate(request, user=plain_user)

    response = query_mandate_from_telebirr(request)

    assert response.status_code == 403


def test_query_mandate_from_telebirr_rejects_anonymous(db):
    request = factory.get('/admin/direct-debit/query-mandate/?payer_msisdn=251911223344')

    response = query_mandate_from_telebirr(request)

    assert response.status_code in (401, 403)
