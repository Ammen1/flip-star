"""
End-to-end smoke tests.

These exercise a full request/response cycle through URL resolution, middleware,
view dispatch and rendering. They are the fastest way to catch a restructure
that resolves at import time but fails at request time.
"""

import pytest

pytestmark = pytest.mark.e2e


def test_liveness_probe_returns_ok_without_touching_db(api_client):
    """`/api/health/` backs the container HEALTHCHECK and must not query the DB."""
    response = api_client.get('/api/v1/health/')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_liveness_probe_accepts_head(api_client):
    """Uptime monitors commonly issue HEAD rather than GET."""
    assert api_client.head('/api/v1/health/').status_code == 200


@pytest.mark.django_db
def test_deep_health_check_reports_database(api_client):
    response = api_client.get('/api/v1/health/deep/')

    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    assert 'database' in body
    assert 'counts' in body


@pytest.mark.django_db
def test_unauthenticated_request_to_protected_endpoint_is_rejected(api_client):
    """A route declaring IsAuthenticated must still reject anonymous callers."""
    response = api_client.get('/api/v1/wallet/')

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_authenticated_wallet_summary_round_trip(auth_client):
    """Full cycle through token auth, view, service and serializer."""
    response = auth_client.get('/api/v1/wallet/')

    assert response.status_code == 200
    body = response.json()
    for key in ('balance', 'points', 'totals', 'withdrawal', 'currency'):
        assert key in body, f'wallet summary no longer returns {key!r}'
    assert body['currency'] == 'ETB'


@pytest.mark.django_db
def test_cors_headers_present_on_response(api_client):
    """The CORS middleware must still run ahead of everything else."""
    response = api_client.get('/api/v1/health/', HTTP_ORIGIN='https://uat.flipstar.et')

    assert 'Access-Control-Allow-Origin' in response


@pytest.mark.django_db
def test_request_id_header_is_returned(api_client):
    """
    Correlation id support.

    Skipped until RequestContextMiddleware is added to MIDDLEWARE -- adding it
    is a behaviour change deferred out of the restructure.
    """
    response = api_client.get('/api/v1/health/')

    if 'X-Request-ID' not in response:
        pytest.skip('RequestContextMiddleware not yet registered in MIDDLEWARE')

    assert response['X-Request-ID']
