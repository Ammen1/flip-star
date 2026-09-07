"""
Logging in as an organization.

The account is created by Super Admin on the dashboard; this covers what
happens next -- signing in with it and landing on the organization dashboard
rather than being turned away at the door.

The admin console gates on two things (Flipstar-web/admin/AdminApp.jsx):

    handleLogin:     response.user.is_staff || response.user.realm === 'ORGANIZATION'
    checkAdminAuth:  same test, but against getProfile() -> /profile/me/

An organization admin is deliberately *not* staff, so `realm` is the only
thing admitting them. If either endpoint stops reporting it the account still
authenticates, still holds a valid token, and is still bounced to the login
screen -- which looks exactly like a wrong password. Both endpoints are
covered here for that reason.
"""

import json

import fakeredis
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.organization import Organization, UserRealm, UserRole
from api.views.core import UserProfileViewSet, login
from api.views.organizations import create_organization_admin
from common.security.e2e_encryption import decrypt_payload, encrypt_payload, generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


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
def superadmin():
    return User.objects.create_superuser(username='root', email='r@x.com', password='x')


@pytest.fixture
def organization():
    return Organization.objects.create(name='ABC Company', code='ABC', status='active')


@pytest.fixture
def org_admin(superadmin, organization):
    """Created through the Super Admin endpoint -- the dashboard's own path."""
    request = factory.post(
        f'/admin/organizations/{organization.id}/admins/',
        {'username': 'abc_admin', 'password': 'sup3rsecret', 'email': 'admin@abc.com'},
        format='json',
    )
    force_authenticate(request, user=superadmin)
    response = create_organization_admin(request, organization.id)
    assert response.status_code == 201, response.data
    return User.objects.get(username='abc_admin')


@pytest.fixture
def sign_in(server_keys, client_keys):
    """POST /auth/login/ over the encrypted transport a real client uses."""
    client_public_key, client_private_key = client_keys

    def _sign_in(username, password):
        envelope = encrypt_payload(
            {'username': username, 'password': password},
            receiver_public_key_b64=server_keys,
            sender_private_key_b64=client_private_key,
        ).to_dict()
        request = factory.post(
            '/auth/login/',
            data=json.dumps(envelope),
            content_type='application/json',
            HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
        )
        response = login(request)
        return response, _decrypt(response, server_keys, client_private_key)

    return _sign_in


# ---------------------------------------------------------------------------
# Signing in
# ---------------------------------------------------------------------------


def test_the_org_admin_can_sign_in(org_admin, sign_in):
    response, body = sign_in('abc_admin', 'sup3rsecret')

    assert response.status_code == 200, body
    assert body['token']


def test_login_reports_the_realm_that_admits_them(org_admin, sign_in):
    """AdminApp's gate: `response.user.realm === 'ORGANIZATION'`."""
    _, body = sign_in('abc_admin', 'sup3rsecret')

    assert body['user']['realm'] == UserRealm.ORGANIZATION


def test_login_reports_role_and_organization(org_admin, organization, sign_in):
    """What the organization dashboard labels itself with."""
    _, body = sign_in('abc_admin', 'sup3rsecret')

    assert body['user']['role'] == UserRole.ADMIN
    assert body['user']['organization'] == {'id': organization.id, 'name': 'ABC Company'}


def test_the_org_admin_is_not_staff(org_admin, sign_in):
    """
    So `is_staff` cannot be what lets them in.

    This is what makes the realm check load-bearing rather than belt-and-braces
    -- and what routes them to the organization dashboard instead of the Super
    Admin console.
    """
    _, body = sign_in('abc_admin', 'sup3rsecret')

    assert body['user']['is_staff'] is False
    assert body['user']['is_superuser'] is False


def test_a_wrong_password_is_still_refused(org_admin, sign_in):
    response, _ = sign_in('abc_admin', 'wrong')

    assert response.status_code == 401


def test_they_can_sign_in_by_email(org_admin, sign_in):
    """The console's field is labelled email; login accepts either."""
    response, body = sign_in('admin@abc.com', 'sup3rsecret')

    assert response.status_code == 200, body
    assert body['user']['realm'] == UserRealm.ORGANIZATION


# ---------------------------------------------------------------------------
# Staying signed in
# ---------------------------------------------------------------------------


def test_the_session_survives_a_page_refresh(org_admin, organization):
    """
    checkAdminAuth re-reads /profile/me/ on load and re-applies the same gate.

    If this payload omitted `realm`, the account would sign in successfully and
    then be thrown out on the next refresh.
    """
    request = factory.get('/profile/me/')
    force_authenticate(request, user=org_admin)
    response = UserProfileViewSet.as_view({'get': 'me'})(request)

    assert response.status_code == 200
    user = response.data['user']
    assert user['realm'] == UserRealm.ORGANIZATION
    assert user['role'] == UserRole.ADMIN
    assert user['organization']['id'] == organization.id


def test_an_ordinary_member_is_not_admitted(sign_in):
    """The gate still keeps everyone else out."""
    User.objects.create_user(username='someone', password='sup3rsecret')

    _, body = sign_in('someone', 'sup3rsecret')

    assert body['user']['realm'] == UserRealm.MEMBER
    assert body['user']['is_staff'] is False
