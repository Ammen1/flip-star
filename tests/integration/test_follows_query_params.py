"""
The follows list, and what it does with a malformed user id.

`GET /api/v1/follows/?follower=undefined` returned a 500. The id goes straight
into a filter on an integer column, so a non-numeric value raised ValueError
deep inside the ORM -- past any handler that could describe it -- and surfaced
as an unhandled exception with a stack trace in the logs.

The value arrives as the literal string "undefined" because a client
interpolated an id it did not have yet. That is a malformed request, so it is
answered as one: 400, naming the parameter. Any client could otherwise 500 the
server with `?follower=abc`.
"""

import fakeredis
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.core import Follow
from api.views.core import FollowViewSet
from common.security.e2e_encryption import generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.django_db

list_view = FollowViewSet.as_view({'get': 'list'})


@pytest.fixture
def server_keys(db):
    """The viewset carries encrypted transport; without server keys it 503s."""
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def client_key():
    """A GET has no body to unseal, so only the header check matters here."""
    public_key, _private_key = generate_keypair()
    return public_key


@pytest.fixture
def alice():
    return User.objects.create_user(username='alice', password='x')


@pytest.fixture
def bob():
    return User.objects.create_user(username='bob', password='x')


@pytest.fixture
def get(server_keys, client_key):
    def _get(user, query=''):
        request = APIRequestFactory().get(f'/follows/{query}', HTTP_X_CLIENT_PUBLIC_KEY=client_key)
        force_authenticate(request, user=user)
        return list_view(request)

    return _get


# ---------------------------------------------------------------------------
# The crash
# ---------------------------------------------------------------------------


def test_follower_undefined_is_a_bad_request_not_a_crash(get, alice):
    """The exact request from the logs."""
    response = get(alice, '?follower=undefined')

    assert response.status_code == 400, response.data


def test_following_undefined_is_a_bad_request_not_a_crash(get, alice):
    """The other branch had the same hole."""
    response = get(alice, '?following=undefined')

    assert response.status_code == 400, response.data


def test_the_refusal_names_the_parameter(get, alice):
    """So the caller can tell which of the two it got wrong."""
    response = get(alice, '?follower=undefined')

    assert 'follower' in response.data


def test_any_non_numeric_value_is_refused(get, alice):
    """Not a special case for the string 'undefined'."""
    for value in ('abc', 'null', 'NaN', '1;DROP TABLE', '1.5', ''):
        response = get(alice, f'?follower={value}')
        # An empty value is falsy, so it falls through to the default branch
        # rather than being refused -- that is the pre-existing behaviour and
        # it does not crash.
        assert response.status_code in (200, 400), f'{value!r} -> {response.status_code}'
        if value:
            assert response.status_code == 400, f'{value!r} should be refused'


# ---------------------------------------------------------------------------
# The normal answers are unchanged
# ---------------------------------------------------------------------------


def test_a_valid_follower_id_lists_who_they_follow(get, alice, bob):
    Follow.objects.create(follower=alice, following=bob)

    response = get(alice, f'?follower={alice.id}')

    assert response.status_code == 200
    assert len(response.data) == 1


def test_a_valid_following_id_lists_their_followers(get, alice, bob):
    Follow.objects.create(follower=alice, following=bob)

    response = get(bob, f'?following={bob.id}')

    assert response.status_code == 200
    assert len(response.data) == 1


def test_a_valid_but_unused_id_is_an_empty_list_not_an_error(get, alice):
    """'Who does user 999999 follow' has an honest answer: nobody."""
    response = get(alice, '?follower=999999')

    assert response.status_code == 200
    assert list(response.data) == []


def test_no_parameters_returns_the_callers_own_following(get, alice, bob):
    Follow.objects.create(follower=alice, following=bob)

    response = get(alice)

    assert response.status_code == 200
    assert len(response.data) == 1


def test_it_still_requires_authentication(server_keys, client_key):
    request = APIRequestFactory().get('/follows/', HTTP_X_CLIENT_PUBLIC_KEY=client_key)
    response = list_view(request)

    assert response.status_code in (401, 403)
