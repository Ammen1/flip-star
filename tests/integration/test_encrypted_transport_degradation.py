"""Does a server-key failure turn a healthy 200 into an HTML 500?"""

from unittest import mock

import fakeredis
import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient

from common.security.e2e_encryption import generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.django_db


@pytest.fixture
def keys(db):
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    pub, priv = generate_keypair()
    yield key_manager.get_public_key(), pub, priv
    key_manager.reset()
    redis_store.reset_client()


def test_server_key_failure_surfaces_as_html_500(keys):
    """
    Simulates the server private key being unavailable (Vault down, or the key
    never provisioned). The renderer runs AFTER DRF's exception handler, so
    anything raised there escapes to Django and produces an HTML 500 page --
    which is exactly what the frontend received in UAT.
    """
    _server_pub, client_pub, _client_priv = keys
    user = User.objects.create_user(username='keyfail_user', password='x')
    c = APIClient()
    c.force_authenticate(user=user)

    with mock.patch(
        'common.security.encrypted_transport.get_server_private_key',
        side_effect=RuntimeError('server key unavailable'),
    ):
        try:
            r = c.get(reverse('subscription-status'), HTTP_X_CLIENT_PUBLIC_KEY=client_pub)
            status = r.status_code
            body = r.content[:200]
            escaped = False
        except Exception as exc:  # noqa: BLE001 - probing what escapes
            status = None
            body = repr(exc)[:200]
            escaped = True

    print('\n  status  =', status)
    print('  escaped =', escaped)
    print('  body    =', body)

    # A key-store outage must be a handled, retryable 503 -- never an
    # unhandled exception that Django turns into a generic HTML 500 page.
    assert not escaped, 'exception escaped DRF and will render as an HTML 500'
    assert status == 503, status
    assert b'encryption_unavailable' in body, body
