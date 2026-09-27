"""Audit N-01: follower counts and follow state without downloading the list.

The web profile page derived all three values from the entire follower list --
`followers.length` for the count and `followers.some(...)` for the Follow
button. Measured cost of that list (FollowSerializer, 20 rows, extrapolated):

    followers    payload    queries
       1,000      0.6 MB      8,050
      10,000      6.2 MB     80,500
      50,000     31.0 MB    402,500

It is also what stopped `FollowViewSet` being paginated: capping the list would
have made the count wrong and shown "Follow" to someone who already follows.

These tests pin the two properties that matter -- the numbers are exact, and the
cost does not grow with the follower count.
"""

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from api.models import Follow
from common.security.e2e_encryption import decrypt_payload
from common.security.encrypted_transport import CLIENT_PUBLIC_KEY_HEADER_NAME

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _get(client, keys, path):
    _server_public, client_public, _client_private = keys
    header = 'HTTP_' + CLIENT_PUBLIC_KEY_HEADER_NAME.upper().replace('-', '_')
    return client.get(path, **{header: client_public})


def _open(response, keys):
    import json

    server_public, _client_public, client_private = keys
    payload = response.json()
    if not isinstance(payload, dict) or 'encrypted' not in payload:
        return payload
    return json.loads(
        decrypt_payload(
            payload['encrypted'],
            payload['nonce'],
            server_public,
            payload['checksum'],
            client_private,
        )
    )


@pytest.fixture
def people(db):
    target = User.objects.create_user(username='fs_target', password='123456')
    viewer = User.objects.create_user(username='fs_viewer', password='123456')
    return target, viewer


def _stats(client, keys, user_id):
    response = _get(client, keys, f'/api/v1/users/{user_id}/follow-stats/')
    assert response.status_code == 200, response.status_code
    return _open(response, keys)


# ── the numbers are exact ────────────────────────────────────────────────────


def test_counts_are_exact(people, encrypted_client_keys):
    target, viewer = people
    for i in range(7):
        follower = User.objects.create_user(username=f'fs_f{i}', password='123456')
        Follow.objects.create(follower=follower, following=target)
    for i in range(3):
        followee = User.objects.create_user(username=f'fs_g{i}', password='123456')
        Follow.objects.create(follower=target, following=followee)

    client = APIClient()
    client.force_authenticate(user=viewer)
    body = _stats(client, encrypted_client_keys, target.id)

    assert body['followers_count'] == 7
    assert body['following_count'] == 3
    assert body['user_id'] == target.id


def test_zero_is_zero(people, encrypted_client_keys):
    target, viewer = people
    client = APIClient()
    client.force_authenticate(user=viewer)
    body = _stats(client, encrypted_client_keys, target.id)
    assert body['followers_count'] == 0
    assert body['following_count'] == 0
    assert body['is_following'] is False


def test_counts_do_not_cross_between_users(people, encrypted_client_keys):
    target, viewer = people
    other = User.objects.create_user(username='fs_other', password='123456')
    Follow.objects.create(follower=viewer, following=target)

    client = APIClient()
    client.force_authenticate(user=viewer)
    assert _stats(client, encrypted_client_keys, target.id)['followers_count'] == 1
    assert _stats(client, encrypted_client_keys, other.id)['followers_count'] == 0


# ── follow state is correct, including past any cap ──────────────────────────


def test_is_following_is_true_when_the_viewer_follows(people, encrypted_client_keys):
    target, viewer = people
    Follow.objects.create(follower=viewer, following=target)

    client = APIClient()
    client.force_authenticate(user=viewer)
    assert _stats(client, encrypted_client_keys, target.id)['is_following'] is True


def test_is_following_is_false_when_the_viewer_does_not(people, encrypted_client_keys):
    target, viewer = people
    other = User.objects.create_user(username='fs_someone', password='123456')
    Follow.objects.create(follower=other, following=target)

    client = APIClient()
    client.force_authenticate(user=viewer)
    assert _stats(client, encrypted_client_keys, target.id)['is_following'] is False


def test_is_following_is_correct_past_the_pagination_cap(people, encrypted_client_keys):
    """The whole point of N-01.

    The viewer is created last, so under the old client-side derivation they
    would sort beyond a 100-row cap and the Follow button would be wrong.
    """
    target, viewer = people
    for i in range(120):
        follower = User.objects.create_user(username=f'fs_bulk{i}', password='123456')
        Follow.objects.create(follower=follower, following=target)
    Follow.objects.create(follower=viewer, following=target)

    client = APIClient()
    client.force_authenticate(user=viewer)
    body = _stats(client, encrypted_client_keys, target.id)

    assert body['followers_count'] == 121, 'the count must be the true total, not a page'
    assert body['is_following'] is True, (
        'the viewer follows the target but sorts past any cap -- this is exactly '
        'the case a client-side derivation got wrong'
    )


def test_your_own_profile_is_not_following_yourself(people, encrypted_client_keys):
    target, _viewer = people
    client = APIClient()
    client.force_authenticate(user=target)
    assert _stats(client, encrypted_client_keys, target.id)['is_following'] is False


# ── the cost does not grow with the follower count ───────────────────────────


def test_query_count_is_flat_regardless_of_followers(people, encrypted_client_keys):
    target, viewer = people
    client = APIClient()
    client.force_authenticate(user=viewer)

    def cost():
        with CaptureQueriesContext(connection) as ctx:
            _get(client, encrypted_client_keys, f'/api/v1/users/{target.id}/follow-stats/')
        return len(ctx.captured_queries)

    small = cost()
    for i in range(60):
        follower = User.objects.create_user(username=f'fs_cost{i}', password='123456')
        Follow.objects.create(follower=follower, following=target)
    large = cost()

    assert large == small, (
        f'cost grew with followers: {small} -> {large}. The point of this endpoint '
        'is that it does not.'
    )


# ── it behaves at the edges ──────────────────────────────────────────────────


def test_unknown_user_is_404(people, encrypted_client_keys):
    _target, viewer = people
    client = APIClient()
    client.force_authenticate(user=viewer)
    response = _get(client, encrypted_client_keys, '/api/v1/users/99999999/follow-stats/')
    assert response.status_code == 404


def test_requires_authentication(people, encrypted_client_keys):
    target, _viewer = people
    response = _get(APIClient(), encrypted_client_keys, f'/api/v1/users/{target.id}/follow-stats/')
    assert response.status_code in (401, 403)


def test_rejects_a_plaintext_request(people):
    """It is an @encrypted_endpoint like the rest of the user-facing surface."""
    target, viewer = people
    client = APIClient()
    client.force_authenticate(user=viewer)
    response = client.get(f'/api/v1/users/{target.id}/follow-stats/')
    assert response.status_code == 400
