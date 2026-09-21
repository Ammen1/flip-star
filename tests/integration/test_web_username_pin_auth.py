"""
Username + PIN authentication for users opening FlipStar in a regular web
browser (the Telebirr Super App keeps its phone/OTP flows -- those are not
under test here; this suite pins the /auth/login/ + /auth/register/ contract
the web screens depend on).

Everything goes through the encrypted transport a real client uses, the same
way tests/integration/test_organization_admin_login.py drives ``login``.
"""

import json

import fakeredis
import pytest
from django.core.cache import cache
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory

from api.views.core import login, register
from common.security.e2e_encryption import decrypt_payload, encrypt_payload, generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()

PIN = '307942'  # passes is_pin_too_weak (strong, non-sequential, non-palindrome)


@pytest.fixture
def server_keys(db):
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def client_keys():
    return generate_keypair()


@pytest.fixture(autouse=True)
def _clean_throttle_cache():
    """The login failure counter lives in Django's cache; keep tests isolated."""
    cache.clear()
    yield
    cache.clear()


def _decrypt(response, server_public_key, client_private_key):
    response.render()
    envelope = json.loads(response.content)
    if 'encrypted' not in envelope:
        # An error raised before the renderer sealed anything.
        return envelope
    plaintext = decrypt_payload(
        envelope['encrypted'],
        envelope['nonce'],
        server_public_key,
        envelope['checksum'],
        client_private_key,
    )
    return json.loads(plaintext)


@pytest.fixture
def transport(server_keys, client_keys):
    """Call an @encrypted_endpoint view the way a real client would."""
    client_public_key, client_private_key = client_keys

    def _call(view, payload, path='/x'):
        envelope = encrypt_payload(
            payload,
            receiver_public_key_b64=server_keys,
            sender_private_key_b64=client_private_key,
        ).to_dict()
        request = factory.post(
            path,
            data=json.dumps(envelope),
            content_type='application/json',
            HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
        )
        response = view(request)
        return response, _decrypt(response, server_keys, client_private_key)

    return _call


# ---------------------------------------------------------------------------
# Registration (/auth/register/)
# ---------------------------------------------------------------------------


def test_register_creates_an_account_with_a_username_and_pin(transport):
    response, body = transport(
        register,
        {'username': 'webuser', 'password': PIN},
        path='/api/v1/auth/register/',
    )

    assert response.status_code == 201, body
    assert body['user']['username'] == 'webuser'
    assert body['token']
    assert User.objects.filter(username='webuser').exists()

    user = User.objects.get(username='webuser')
    assert user.check_password(PIN)


def test_register_does_not_echo_the_pin(transport):
    """The PIN must never round-trip in the API response."""
    response, body = transport(
        register,
        {'username': 'webuser2', 'password': PIN},
        path='/api/v1/auth/register/',
    )

    assert response.status_code == 201, body
    assert PIN not in json.dumps(body)


def test_register_rejects_a_weak_pin(transport):
    response, body = transport(
        register,
        {'username': 'weakpin', 'password': '123456'},
        path='/api/v1/auth/register/',
    )

    assert response.status_code == 400
    assert not User.objects.filter(username='weakpin').exists()


def test_register_rejects_a_malformed_pin(transport):
    for bad in ('', '12345', 'abcdef', '1234567'):
        response, _ = transport(
            register,
            {'username': 'malformed', 'password': bad},
            path='/api/v1/auth/register/',
        )
        assert response.status_code == 400, f'PIN {bad!r} should be refused'


def test_register_answers_a_taken_username_with_a_clean_409(transport):
    User.objects.create_user(username='ammen', password=PIN)

    response, body = transport(
        register,
        {'username': 'ammen', 'password': PIN},
        path='/api/v1/auth/register/',
    )

    assert response.status_code == 409
    assert body['code'] == 'USERNAME_TAKEN'
    assert 'choose another' in body['error']
    assert 'constraint' not in body['error']


def test_register_refuses_a_case_variant_username(transport):
    User.objects.create_user(username='ammen', password=PIN)

    response, body = transport(
        register,
        {'username': 'Ammen', 'password': PIN},
        path='/api/v1/auth/register/',
    )

    assert response.status_code == 409
    assert body['code'] == 'USERNAME_TAKEN'


# ---------------------------------------------------------------------------
# Login (/auth/login/)
# ---------------------------------------------------------------------------


@pytest.fixture
def webuser(db):
    return User.objects.create_user(
        username='webuser', email='webuser@example.com', password=PIN
    )


def test_login_with_username_and_pin_succeeds(webuser, transport):
    response, body = transport(
        login,
        {'username': 'webuser', 'password': PIN},
        path='/api/v1/auth/login/',
    )

    assert response.status_code == 200, body
    assert body['user']['username'] == 'webuser'
    assert body['token']


def test_login_does_not_echo_the_pin(webuser, transport):
    response, body = transport(
        login,
        {'username': 'webuser', 'password': PIN},
        path='/api/v1/auth/login/',
    )

    assert response.status_code == 200
    assert PIN not in json.dumps(body)


def test_login_accepts_email_as_username(webuser, transport):
    """The admin console already logs in by email; keep accepting it."""
    response, body = transport(
        login,
        {'username': 'webuser@example.com', 'password': PIN},
        path='/api/v1/auth/login/',
    )

    assert response.status_code == 200, body
    assert body['user']['username'] == 'webuser'


def test_login_with_wrong_pin_returns_attempts_remaining(webuser, transport):
    response, body = transport(
        login,
        {'username': 'webuser', 'password': '000000'},
        path='/api/v1/auth/login/',
    )

    assert response.status_code == 401
    assert body['error'] == 'Invalid credentials'
    assert body['attempts_remaining'] == 5


def test_login_with_unknown_username_returns_attempts_remaining(transport):
    response, body = transport(
        login,
        {'username': 'nobody', 'password': PIN},
        path='/api/v1/auth/login/',
    )

    assert response.status_code == 401
    assert body['error'] == 'Invalid credentials'
    assert body['attempts_remaining'] == 5


def test_login_locks_out_after_six_failed_attempts(webuser, transport):
    for _ in range(6):
        response, body = transport(
            login,
            {'username': 'webuser', 'password': '000000'},
            path='/api/v1/auth/login/',
        )

    assert response.status_code == 429


def test_login_clears_failures_on_success(webuser, transport):
    transport(
        login,
        {'username': 'webuser', 'password': '000000'},
        path='/api/v1/auth/login/',
    )
    response, _ = transport(
        login,
        {'username': 'webuser', 'password': PIN},
        path='/api/v1/auth/login/',
    )
    assert response.status_code == 200

    # The failure counter is cleared, so a later mistake starts at 5 again.
    response, body = transport(
        login,
        {'username': 'webuser', 'password': '000000'},
        path='/api/v1/auth/login/',
    )
    assert response.status_code == 401
    assert body['attempts_remaining'] == 5


def test_wrong_pin_does_not_leak_account_details(webuser, transport):
    """An existing username with a wrong PIN must look like a failed login,
    never like 'this account exists'."""
    response, body = transport(
        login,
        {'username': 'webuser', 'password': '000000'},
        path='/api/v1/auth/login/',
    )

    assert response.status_code == 401
    assert 'user' not in body
    assert body['error'] == 'Invalid credentials'


def test_login_requires_username_and_pin(webuser, transport):
    for bad in (
        {'username': 'webuser'},
        {'password': PIN},
        {},
    ):
        response, _ = transport(login, bad, path='/api/v1/auth/login/')
        assert response.status_code == 400, bad