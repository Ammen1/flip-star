"""
Explore's category and time filters, through /explorer/trending/.

What was wrong
--------------
Selecting a category on the Explore page did not reliably filter the feed:

  - An unknown category skipped the filter and returned every post. A slug
    that did not match looked exactly like a filter that "does nothing".
  - ``offset`` was never read. Every infinite-scroll request returned page
    one again; the client de-duplicated by id and appended nothing, so a
    category never got past its first twelve posts.
  - Any failure came back as ``200 []``, which the page rendered as "nothing
    trending yet" -- the same screen as a category with no posts.

The category value is now resolved once (api/services/feed_filters.py) for
both trending endpoints: an id (what the web client sends), a slug (what older
clients send), or all / trending / nothing for no filter.
"""

from datetime import timedelta

import fakeredis
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import Category, Reel
from common.security.e2e_encryption import generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


@pytest.fixture
def server_keys(db):
    """The trending views carry @encrypted_endpoint, so the server needs keys."""
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
    return User.objects.create_user(username='explore_author', password='x')


@pytest.fixture
def viewer():
    return User.objects.create_user(username='explore_viewer', password='x')


@pytest.fixture
def dance():
    return Category.objects.create(name='Dance', slug='dance', order=1)


@pytest.fixture
def music():
    return Category.objects.create(name='Music', slug='music', order=2)


@pytest.fixture
def comedy():
    return Category.objects.create(name='Comedy', slug='comedy', order=3)


def post(author, category=None, *, age=timedelta(hours=1), votes=0):
    """A post of a given age. created_at is auto_now_add, so it is set after."""
    reel = Reel.objects.create(user=author, caption='post', category=category)
    Reel.objects.filter(pk=reel.pk).update(created_at=timezone.now() - age, votes=votes)
    return reel


def trending(viewer, client_keys, view=None, **params):
    """Call the explorer feed as the web client does: a GET with the query string.

    X-Client-Public-Key is required because @encrypted_endpoint seals the
    response; response.data is still the plain payload before rendering.
    """
    from api.views.core import get_trending_reels

    query = '&'.join(f'{k}={v}' for k, v in params.items() if v is not None)
    client_public_key, _ = client_keys
    request = factory.get(
        f'/explorer/trending/?{query}', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key
    )
    force_authenticate(request, user=viewer)
    return (view or get_trending_reels)(request)


def ids(response):
    assert response.status_code == 200, response.data
    return [row['id'] for row in response.data]


# ---------------------------------------------------------------------------
# Selecting a category filters the feed
# ---------------------------------------------------------------------------


def test_a_category_id_returns_only_that_categorys_posts(
    author, viewer, dance, music, server_keys, client_keys
):
    wanted = post(author, dance)
    post(author, music)
    post(author, None)

    returned = ids(trending(viewer, client_keys, category=dance.id))

    assert returned == [wanted.id]


def test_a_slug_still_works_for_existing_clients(
    author, viewer, dance, music, server_keys, client_keys
):
    """Older web builds and the mobile app send slugs; they must keep working."""
    wanted = post(author, dance)
    post(author, music)

    assert ids(trending(viewer, client_keys, category='dance')) == [wanted.id]


@pytest.mark.parametrize('value', ['all', 'trending', '', None])
def test_no_category_means_every_category(
    author, viewer, dance, music, server_keys, client_keys, value
):
    """
    ``trending`` is what the mobile Explore screen sends for its only tab;
    ``all`` is the web's "All" chip. Neither may be taken for a category.
    """
    expected = {post(author, dance).id, post(author, music).id, post(author, None).id}

    assert set(ids(trending(viewer, client_keys, category=value))) == expected


def test_choosing_all_after_a_category_lifts_the_restriction(
    author, viewer, dance, music, server_keys, client_keys
):
    a = post(author, dance)
    b = post(author, music)

    assert ids(trending(viewer, client_keys, category=dance.id)) == [a.id]
    assert set(ids(trending(viewer, client_keys, category='all'))) == {a.id, b.id}


@pytest.mark.parametrize(
    'value',
    ['no-such-category', '999999', '99999999999999999999', 'retired'],
)
def test_an_unknown_or_inactive_category_is_rejected_not_ignored(
    author, viewer, dance, server_keys, client_keys, value
):
    """
    400 rather than the whole feed. Serving everything for a category that
    does not exist looks like the filter ran and matched everything.
    """
    Category.objects.create(name='Retired', slug='retired', is_active=False)
    post(author, dance)

    response = trending(viewer, client_keys, category=value)

    assert response.status_code == 400
    assert response.data['code'] == 'invalid_category'


# ---------------------------------------------------------------------------
# Category and time together
# ---------------------------------------------------------------------------


@pytest.fixture
def library(author, dance, music):
    """Posts of known categories and ages."""
    return {
        'dance_2h': post(author, dance, age=timedelta(hours=2)),
        'dance_3d': post(author, dance, age=timedelta(days=3)),
        'dance_20d': post(author, dance, age=timedelta(days=20)),
        'dance_60d': post(author, dance, age=timedelta(days=60)),
        'music_2h': post(author, music, age=timedelta(hours=2)),
        'music_3d': post(author, music, age=timedelta(days=3)),
        'music_20d': post(author, music, age=timedelta(days=20)),
        'plain_3d': post(author, None, age=timedelta(days=3)),
    }


@pytest.mark.parametrize(
    ('category', 'time_range', 'expected'),
    [
        ('dance', '24h', {'dance_2h'}),
        ('dance', '7d', {'dance_2h', 'dance_3d'}),
        ('dance', '30d', {'dance_2h', 'dance_3d', 'dance_20d'}),
        ('music', '24h', {'music_2h'}),
        ('music', '7d', {'music_2h', 'music_3d'}),
        ('music', '30d', {'music_2h', 'music_3d', 'music_20d'}),
        ('all', '24h', {'dance_2h', 'music_2h'}),
        ('all', '7d', {'dance_2h', 'dance_3d', 'music_2h', 'music_3d', 'plain_3d'}),
    ],
)
def test_category_and_time_range_combine(
    viewer, library, dance, music, server_keys, client_keys, category, time_range, expected
):
    category_value = {'dance': dance.id, 'music': music.id, 'all': 'all'}[category]

    returned = set(
        ids(trending(viewer, client_keys, category=category_value, time_range=time_range))
    )

    assert returned == {library[name].id for name in expected}


def test_a_category_with_nothing_in_the_window_is_an_empty_feed_not_an_error(
    viewer, library, comedy, server_keys, client_keys
):
    """Empty is a valid answer -- the client shows its empty state for it."""
    response = trending(viewer, client_keys, category=comedy.id, time_range='30d')

    assert response.status_code == 200
    assert response.data == []


def test_the_default_window_is_seven_days(viewer, library, dance, server_keys, client_keys):
    returned = set(ids(trending(viewer, client_keys, category=dance.id)))

    assert returned == {library['dance_2h'].id, library['dance_3d'].id}


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_pages_continue_within_the_same_category(
    author, viewer, dance, music, server_keys, client_keys
):
    """
    Page two used to be page one again. Every page now carries on from the
    last, stays inside the category, and repeats nothing -- including when
    posts tie on votes and time, which is where offset paging usually slips.
    """
    moment = timedelta(hours=1)
    dance_posts = {post(author, dance, age=moment, votes=5).id for _ in range(5)}
    for _ in range(3):
        post(author, music, age=moment, votes=5)

    pages = [
        ids(trending(viewer, client_keys, category=dance.id, limit=2, offset=o))
        for o in (0, 2, 4, 6)
    ]

    assert [len(p) for p in pages] == [2, 2, 1, 0]
    seen = [i for page in pages for i in page]
    assert len(seen) == len(set(seen)), 'a post appeared on two pages'
    assert set(seen) == dance_posts


def test_pages_follow_the_ranking(author, viewer, dance, server_keys, client_keys):
    ranked = [post(author, dance, votes=v).id for v in (50, 40, 30, 20)]

    first = ids(trending(viewer, client_keys, category=dance.id, limit=2, offset=0))
    second = ids(trending(viewer, client_keys, category=dance.id, limit=2, offset=2))

    assert first + second == ranked


def test_a_deep_offset_ends_the_feed(author, viewer, dance, server_keys, client_keys):
    post(author, dance)

    assert ids(trending(viewer, client_keys, category=dance.id, offset=5000)) == []


@pytest.mark.parametrize(('limit', 'offset'), [('abc', 'xyz'), ('-3', '-7'), ('500', '0')])
def test_odd_paging_values_fall_back_to_sane_ones(
    author, viewer, dance, server_keys, client_keys, limit, offset
):
    post(author, dance)

    response = trending(viewer, client_keys, category=dance.id, limit=limit, offset=offset)

    assert response.status_code == 200
    assert len(response.data) == 1


# ---------------------------------------------------------------------------
# Failure
# ---------------------------------------------------------------------------


def test_a_failure_is_an_error_not_an_empty_feed(
    author, viewer, dance, server_keys, client_keys, monkeypatch
):
    """
    ``200 []`` read as "nothing here yet". A broken request has to look broken,
    so the client can say so and offer a retry.
    """
    import api.views.core as core

    def explode(*args, **kwargs):
        raise RuntimeError('database went away')

    post(author, dance)
    monkeypatch.setattr(core, 'ReelSerializer', explode)

    response = trending(viewer, client_keys, category=dance.id)

    assert response.status_code == 500
    assert response.data['code'] == 'trending_failed'


# ---------------------------------------------------------------------------
# The other trending endpoint agrees
# ---------------------------------------------------------------------------


def test_reels_trending_accepts_the_same_category_values(
    author, viewer, dance, music, server_keys, client_keys
):
    from api.views.reels import reels_trending

    wanted = post(author, dance)
    post(author, music)

    assert ids(trending(viewer, client_keys, view=reels_trending, category=dance.id)) == [wanted.id]
    assert ids(trending(viewer, client_keys, view=reels_trending, category='dance')) == [wanted.id]
    rejected = trending(viewer, client_keys, view=reels_trending, category='424242')
    assert rejected.status_code == 400
    assert rejected.data['code'] == 'invalid_category'
