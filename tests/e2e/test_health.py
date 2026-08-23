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
def test_wallet_summary_rejects_an_unencrypted_request(auth_client):
    """
    ``/api/v1/wallet/`` is an encrypted endpoint and must refuse plaintext.

    ``api/views/wallet.py::wallet_summary`` carries ``@encrypted_endpoint``,
    which calls ``require_client_public_key()`` before the view body runs and
    raises ``DecryptionError`` (HTTP 400) when ``X-Client-Public-Key`` is
    absent. That is the designed security contract, not a bug -- so this
    asserts the rejection rather than treating it as a failure.
    """
    response = auth_client.get('/api/v1/wallet/')

    assert response.status_code == 400


@pytest.mark.django_db
def test_authenticated_wallet_summary_round_trip(auth_client, encrypted_client_keys):
    """
    Full cycle through token auth, decryption, view, service and re-encryption.

    This previously issued a plain GET and asserted a 200 with a plaintext
    body. It failed with 400 -- correctly: ``wallet_summary`` was wired to
    ``@encrypted_endpoint`` (the decorator's own test module still claims "no
    real endpoint uses these yet", which is now stale), so a plaintext request
    is rejected before the view runs. Loosening the endpoint to satisfy the
    old assertion would have removed end-to-end encryption from a wallet
    endpoint, so the test was corrected to perform the encrypted round trip
    its name always promised instead.
    """
    import json

    from common.security.e2e_encryption import decrypt_payload
    from common.security.encrypted_transport import CLIENT_PUBLIC_KEY_HEADER_NAME

    server_public_key, client_public_key, client_private_key = encrypted_client_keys

    response = auth_client.get(
        '/api/v1/wallet/',
        **{'HTTP_' + CLIENT_PUBLIC_KEY_HEADER_NAME.upper().replace('-', '_'): client_public_key},
    )

    assert response.status_code == 200

    envelope = response.json()
    assert set(envelope) == {
        'encrypted',
        'nonce',
        'checksum',
    }, 'wallet summary must come back as an encrypted envelope, not plaintext'

    body = json.loads(
        decrypt_payload(
            envelope['encrypted'],
            envelope['nonce'],
            server_public_key,
            envelope['checksum'],
            client_private_key,
        )
    )
    for key in ('balance', 'points', 'totals', 'withdrawal', 'currency'):
        assert key in body, f'wallet summary no longer returns {key!r}'
    assert body['currency'] == 'ETB'


@pytest.mark.django_db
def test_cors_headers_present_on_response(api_client):
    """The CORS middleware must still run ahead of everything else."""
    response = api_client.get('/api/v1/health/', HTTP_ORIGIN='https://api.uat.flipstar.et')

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
