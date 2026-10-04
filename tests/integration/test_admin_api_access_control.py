"""
Who can reach the admin API -- the server-side half of the private dashboard.

Moving the dashboard to its own hostname hides nothing on its own: the API it
calls is the same API, served under the public hosts too (flipstar.et/api,
api.uat.flipstar.et). So the guarantee has to live here, and these tests hold
it from the outside, with real tokens.

Real tokens matter. AdminPathGuardMiddleware runs before DRF and resolves the
Authorization header itself; APIClient.force_authenticate() only reaches DRF,
so a test using it sees 401 everywhere and proves nothing about the
middleware at all.

The bug these were written against: the API is mounted twice -- /api/ and
/api/v1/ -- and the middleware guarded only /api/v1/admin/. Through /api/admin/
an ordinary signed-in user reached the admin views directly, where several are
guarded by nothing more than IsAuthenticated.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models.subscription import AdminRole

pytestmark = pytest.mark.django_db

MOUNTS = ['/api/v1/', '/api/']

# Admin routes whose view-level guard is IsAuthenticated alone -- the ones the
# middleware is the only real gate for. Ids that do not exist: a 403 means the
# request was turned away at the door; a 404/400 means it got into the view.
DOOR_ONLY = [
    ('get', 'admin/master-campaigns/999/participants/'),
    ('get', 'admin/organizations/999/coin-config/'),
    ('post', 'admin/contest/judge/999/'),
    ('delete', 'admin/subscriptions/999/'),
    ('get', 'admin/crm/transactions/'),
    ('get', 'admin/subscriptions/revenue/'),
    ('get', 'admin/reports/stats/'),
]


def client(user=None):
    c = APIClient()
    if user is not None:
        token, _ = Token.objects.get_or_create(user=user)
        c.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return c


@pytest.fixture
def ordinary():
    return User.objects.create_user(username='ordinary', password='123456')


@pytest.fixture
def staff():
    return User.objects.create_user(username='staffer', password='123456', is_staff=True)


@pytest.mark.parametrize('mount', MOUNTS)
@pytest.mark.parametrize('method, path', DOOR_ONLY)
def test_anonymous_is_turned_away(mount, method, path):
    assert getattr(client(), method)(mount + path, {}, format='json').status_code == 401


@pytest.mark.parametrize('mount', MOUNTS)
@pytest.mark.parametrize('method, path', DOOR_ONLY)
def test_an_ordinary_user_is_turned_away_on_both_mounts(ordinary, mount, method, path):
    """The regression: /api/admin/ used to let these straight through."""
    r = getattr(client(ordinary), method)(mount + path, {}, format='json')
    assert r.status_code == 403, f'{method.upper()} {mount}{path} -> {r.status_code}'


@pytest.mark.parametrize('mount', MOUNTS)
def test_staff_get_in_on_both_mounts(staff, mount):
    r = client(staff).get(mount + 'admin/reports/stats/')
    assert r.status_code == 200, r.status_code


def test_both_mounts_answer_an_ordinary_user_identically(ordinary):
    """A second path to the same view must not be a second policy."""
    c = client(ordinary)
    for method, path in DOOR_ONLY:
        a = getattr(c, method)('/api/v1/' + path, {}, format='json').status_code
        b = getattr(c, method)('/api/' + path, {}, format='json').status_code
        assert a == b, f'{path}: /api/v1/ -> {a} but /api/ -> {b}'


@pytest.mark.parametrize('mount', MOUNTS)
def test_an_expired_or_bogus_token_is_turned_away(mount):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION='Token not-a-real-token')
    assert c.get(mount + 'admin/reports/stats/').status_code == 401


@pytest.mark.parametrize('mount', MOUNTS)
def test_a_read_only_admin_cannot_write(staff, mount):
    AdminRole.objects.create(
        user=staff, role='support_agent', permission_level='read_only', is_active=True
    )
    r = client(staff).post(mount + 'admin/reports/999/moderate/', {}, format='json')
    assert r.status_code == 403, r.status_code


@pytest.mark.parametrize('mount', MOUNTS)
def test_a_read_only_admin_can_still_read(staff, mount):
    AdminRole.objects.create(
        user=staff, role='support_agent', permission_level='read_only', is_active=True
    )
    assert client(staff).get(mount + 'admin/reports/stats/').status_code == 200


def test_preflight_is_not_blocked():
    """CORS preflights carry no credentials; the CORS middleware answers them."""
    r = APIClient().options('/api/admin/reports/stats/')
    assert r.status_code != 401


# --- ADMIN_ALLOWED_IPS -------------------------------------------------------
#
# The network half. Staff tokens work from anywhere a token can be typed in;
# once ADMIN_ALLOWED_IPS is set, the admin API answers only the allow-listed
# networks -- on every hostname, since it is enforced here and not by host.

STAFF_NET = '198.51.100.0/24'  # TEST-NET-2: documentation addresses only
INSIDE = '198.51.100.7'
OUTSIDE = '203.0.113.9'  # TEST-NET-3
STATS = 'admin/reports/stats/'


def test_unset_means_no_network_restriction(staff, settings):
    """Default: exactly the behaviour before the setting existed."""
    settings.ADMIN_ALLOWED_IPS = []
    r = client(staff).get('/api/v1/' + STATS, REMOTE_ADDR=OUTSIDE)
    assert r.status_code == 200, r.status_code


@pytest.mark.parametrize('mount', MOUNTS)
def test_staff_inside_the_allow_list_get_in(staff, settings, mount):
    settings.ADMIN_ALLOWED_IPS = [STAFF_NET]
    assert client(staff).get(mount + STATS, REMOTE_ADDR=INSIDE).status_code == 200


@pytest.mark.parametrize('mount', MOUNTS)
def test_a_valid_staff_token_from_outside_is_refused(staff, settings, mount):
    settings.ADMIN_ALLOWED_IPS = [STAFF_NET]
    r = client(staff).get(mount + STATS, REMOTE_ADDR=OUTSIDE)
    assert r.status_code == 403, r.status_code


def test_outside_is_refused_before_authentication(settings):
    """Anonymous from outside is a 403, not a 401: nothing is looked up."""
    settings.ADMIN_ALLOWED_IPS = [STAFF_NET]
    assert APIClient().get('/api/v1/' + STATS, REMOTE_ADDR=OUTSIDE).status_code == 403


def test_a_forged_forwarded_for_does_not_get_in(staff, settings):
    """X-Forwarded-For counts only when the direct peer is a trusted proxy."""
    settings.ADMIN_ALLOWED_IPS = [STAFF_NET]
    settings.TRUSTED_PROXY_IPS = ['10.42.0.0/16']
    r = client(staff).get('/api/v1/' + STATS, REMOTE_ADDR=OUTSIDE, HTTP_X_FORWARDED_FOR=INSIDE)
    assert r.status_code == 403, r.status_code


def test_the_address_the_ingress_forwards_is_the_one_checked(staff, settings):
    """In the cluster the direct peer is ingress-nginx on the pod network."""
    settings.ADMIN_ALLOWED_IPS = [STAFF_NET]
    settings.TRUSTED_PROXY_IPS = ['10.42.0.0/16']
    c = client(staff)
    inside = c.get('/api/v1/' + STATS, REMOTE_ADDR='10.42.0.15', HTTP_X_FORWARDED_FOR=INSIDE)
    outside = c.get('/api/v1/' + STATS, REMOTE_ADDR='10.42.0.15', HTTP_X_FORWARDED_FOR=OUTSIDE)
    assert (inside.status_code, outside.status_code) == (200, 403)


def test_an_unusable_allow_list_refuses_everyone(staff, settings):
    """A typo must not quietly switch the restriction off."""
    settings.ADMIN_ALLOWED_IPS = ['198.51.100.0/33', 'office-network']
    r = client(staff).get('/api/v1/' + STATS, REMOTE_ADDR=INSIDE)
    assert r.status_code == 403, r.status_code


@pytest.mark.parametrize('path', ['/api/v1/health/', '/api/v1/settings/public/', '/api/health/'])
def test_the_allow_list_covers_only_the_admin_api(ordinary, settings, path):
    """Subscribers keep using the rest of the API from anywhere: a non-admin
    path answers exactly as it did before the list was set."""
    c = client(ordinary)
    settings.ADMIN_ALLOWED_IPS = []
    before = c.get(path, REMOTE_ADDR=OUTSIDE).status_code
    settings.ADMIN_ALLOWED_IPS = [STAFF_NET]
    after = c.get(path, REMOTE_ADDR=OUTSIDE).status_code
    assert after == before, f'{path}: {before} before the allow-list, {after} after'
