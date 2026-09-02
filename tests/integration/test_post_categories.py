"""
Post categories: assignment on creation, filtering on Explore and Trending.

The Category model and Reel.category FK already existed; what was missing was
server-side validation and filtering on the trending feed. These cover the four
cases that matter:

  creation      a valid category is persisted and surfaces in the API
  filtering     a category filter returns only that category's posts
  invalid       an unknown category is rejected, not silently dropped
  existing      posts created before categories (category=None) still work

The invalid case is the one with history. create_post used to catch
Category.DoesNotExist and carry on, so a stale or mistyped id produced a 201
and an uncategorised post -- which then never appeared under any Explore
filter, with nothing in the response to say why.
"""

import fakeredis
import pytest
from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import Category, Reel
from api.views.reels import reels_trending
from common.security.e2e_encryption import generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


@pytest.fixture
def _server_keys(db):
    """reels_trending carries @encrypted_endpoint, so the server needs keys."""
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


@pytest.fixture
def author():
    return User.objects.create_user(username='cat_author', password='x')


@pytest.fixture
def dance():
    return Category.objects.create(name='Dance', slug='dance', order=1)


@pytest.fixture
def comedy():
    return Category.objects.create(name='Comedy', slug='comedy', order=2)


@pytest.fixture
def retired():
    """An inactive category -- present in the table, not selectable."""
    return Category.objects.create(name='Retired', slug='retired', is_active=False)


def _reel(author, category=None, caption='post'):
    return Reel.objects.create(user=author, caption=caption, category=category)


def _trending(user, client_keys, query=''):
    """
    Call the trending feed the way the client does.

    No request envelope -- it is a GET with no body -- but
    X-Client-Public-Key is required, because @encrypted_endpoint seals the
    RESPONSE. Without it the view answers 400 decryption_failed before running.
    Assertions still read response.data: DRF holds the plain payload until
    render time.
    """
    client_public_key, _ = client_keys
    request = factory.get(f'/reels/trending/{query}', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)
    force_authenticate(request, user=user)
    return reels_trending(request)


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------


def test_category_is_persisted_on_the_post(author, dance):
    reel = _reel(author, dance)

    reel.refresh_from_db()
    assert reel.category == dance
    assert reel.category.slug == 'dance'


def test_a_post_without_a_category_is_valid(author):
    """Category is optional; the field is null=True and must stay so."""
    reel = _reel(author)

    reel.refresh_from_db()
    assert reel.category is None


def test_deleting_a_category_keeps_the_post(author, dance):
    """
    on_delete=SET_NULL, not CASCADE.

    Removing a category must never remove user content -- the post survives
    and simply becomes uncategorised.
    """
    reel = _reel(author, dance)
    dance.delete()

    reel.refresh_from_db()
    assert reel.category is None
    assert Reel.objects.filter(id=reel.id).exists()


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def test_trending_filters_to_the_requested_category(
    author, dance, comedy, _server_keys, client_keys
):
    wanted = _reel(author, dance, caption='a dance post')
    _reel(author, comedy, caption='a comedy post')

    response = _trending(author, client_keys, '?category=dance')

    assert response.status_code == 200
    returned = {r['id'] for r in response.data}
    assert returned == {wanted.id}


def test_trending_without_a_category_returns_everything(
    author, dance, comedy, _server_keys, client_keys
):
    """Existing callers pass no category and must see the unfiltered feed."""
    a = _reel(author, dance)
    b = _reel(author, comedy)
    c = _reel(author, None)

    response = _trending(author, client_keys)

    assert response.status_code == 200
    assert {r['id'] for r in response.data} >= {a.id, b.id, c.id}


def test_trending_treats_all_as_no_filter(author, dance, _server_keys, client_keys):
    """The frontend sends category=all for "everything"."""
    a = _reel(author, dance)
    b = _reel(author, None)

    response = _trending(author, client_keys, '?category=all')

    assert response.status_code == 200
    assert {r['id'] for r in response.data} >= {a.id, b.id}


def test_uncategorised_posts_are_excluded_by_a_category_filter(
    author, dance, _server_keys, client_keys
):
    """Posts predating categories must not leak into a filtered view."""
    legacy = _reel(author, None, caption='from before categories existed')
    current = _reel(author, dance)

    response = _trending(author, client_keys, '?category=dance')

    returned = {r['id'] for r in response.data}
    assert current.id in returned
    assert legacy.id not in returned


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------


def test_unknown_category_is_rejected(author, dance, _server_keys, client_keys):
    """
    400, not a silently unfiltered feed.

    Returning every post for an unknown slug would look like the filter ran
    and matched everything, which is the harder failure to notice.
    """
    _reel(author, dance)

    response = _trending(author, client_keys, '?category=does-not-exist')

    assert response.status_code == 400
    assert response.data['code'] == 'invalid_category'


def test_inactive_category_is_rejected(author, retired, _server_keys, client_keys):
    """An inactive category is not selectable, even though the row exists."""
    _reel(author, retired)

    response = _trending(author, client_keys, '?category=retired')

    assert response.status_code == 400
    assert response.data['code'] == 'invalid_category'


# ---------------------------------------------------------------------------
# API shape
# ---------------------------------------------------------------------------


def test_serializer_exposes_category_name_and_slug(author, dance, _server_keys, client_keys):
    """
    The client needs a label without a second request.

    ReelSerializer carries category, category_name and category_slug; dropping
    either would force the frontend to resolve ids against /categories/.
    """
    _reel(author, dance)

    response = _trending(author, client_keys, '?category=dance')

    row = response.data[0]
    assert row['category'] == dance.id
    assert row['category_name'] == 'Dance'
    assert row['category_slug'] == 'dance'


def test_category_is_null_in_the_payload_for_uncategorised_posts(author, _server_keys, client_keys):
    _reel(author, None)

    response = _trending(author, client_keys)

    row = next(r for r in response.data if r['category'] is None)
    assert row['category_name'] is None
    assert row['category_slug'] is None


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


def test_category_created_at_index_exists():
    """
    Explore filters by category and orders by recency in the same query, so
    the pair has to be one index -- category alone still leaves a sort.
    """
    index_fields = [tuple(i.fields) for i in Reel._meta.indexes]
    assert ('category', '-created_at') in index_fields


def test_categories_are_ordered_for_display(dance, comedy):
    """Meta.ordering drives the order the picker renders in."""
    names = list(Category.objects.values_list('name', flat=True))
    assert names == ['Dance', 'Comedy']  # order=1, order=2


def test_inactive_categories_are_excluded_from_the_active_set(dance, retired):
    active = list(Category.objects.filter(is_active=True).values_list('slug', flat=True))
    assert 'dance' in active
    assert 'retired' not in active


def test_slug_is_unique():
    """
    The slug is the filter key in the URL, so a duplicate would make
    ?category=<slug> ambiguous.
    """
    Category.objects.create(name='First', slug='dup')
    with pytest.raises(IntegrityError):
        Category.objects.create(name='Second', slug='dup')


def test_recent_posts_only(author, dance, _server_keys, client_keys):
    """reels_trending windows to the last 7 days; older posts drop out."""
    old = _reel(author, dance)
    Reel.objects.filter(id=old.id).update(created_at=timezone.now() - timezone.timedelta(days=30))
    fresh = _reel(author, dance)

    response = _trending(author, client_keys, '?category=dance')

    returned = {r['id'] for r in response.data}
    assert fresh.id in returned
    assert old.id not in returned
