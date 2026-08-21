"""
Regression tests for api/views/client_log.py -- ported from the master
branch, entirely missing in the current project before this change. No
database is needed -- these views only write to the logger.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIRequestFactory

from api.views.client_log import clear_pending_mandate, client_log

pytestmark = pytest.mark.unit

factory = APIRequestFactory()


def test_client_log_accepts_a_well_formed_message():
    request = factory.post('/client-log/', {
        'source': 'camera', 'level': 'error', 'message': 'getUserMedia failed', 'userAgent': 'test-agent',
    }, format='json')

    response = client_log(request)

    assert response.status_code == 200
    assert response.data['ok'] is True


def test_client_log_never_errors_on_missing_fields():
    request = factory.post('/client-log/', {}, format='json')

    response = client_log(request)

    assert response.status_code == 200
    assert response.data['ok'] is True


def test_client_log_truncates_oversized_message():
    request = factory.post('/client-log/', {'message': 'x' * 5000}, format='json')

    response = client_log(request)

    assert response.status_code == 200
    assert response.data['ok'] is True


def test_clear_pending_mandate_returns_the_expected_action():
    request = factory.post('/client-log/clear-pending-mandate/')

    response = clear_pending_mandate(request)

    assert response.status_code == 200
    assert response.data == {'ok': True, 'action': 'clear_local_storage', 'key': 'telebirr_pending_mandate'}
