"""Audit C-01 / P2-4: the feed's query count is flat, and the numbers are right.

Measured before the fix, through the real view:

    GET /api/v1/reels/   1 row -> 5 queries,  5 rows -> 13,  20 rows -> 43
                         marginal cost 2.0 queries per row

Two serializer methods were re-fetching data the queryset had already loaded:

    get_comment_count   obj.comments.count()   ignoring comment_count_db
    get_gift_count      SUM over api_gifttransaction, ignoring the
                        prefetch_related('gifts_received') already paid for

After: 20 rows -> 3 queries anonymous, 4 authenticated. Marginal cost 0.0.

A query ceiling on its own is a trap -- it passes just as well if the values go
wrong -- so the correctness assertions below matter more than the count ones.
"""

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from api.models import Comment, Reel

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

#: Headroom over the measured 3/4 so an unrelated middleware query does not fail
#: this, while still failing loudly if a per-row query returns. At 20 rows a
#: single reintroduced N+1 costs 20.
MAX_QUERIES_ANON = 8
MAX_QUERIES_AUTH = 10


@pytest.fixture
def owner(db):
    return User.objects.create_user(username='budget_owner', password='123456')


def _seed(n, owner):
    return [Reel.objects.create(user=owner, caption=f'r{i}', processed=True) for i in range(n)]


def _rows(response):
    body = response.json()
    return body if isinstance(body, list) else body.get('results', [])


# ── the count is flat ────────────────────────────────────────────────────────


def test_feed_query_count_does_not_grow_with_row_count(owner):
    client = APIClient()
    counts = {}
    for n in (1, 5, 20):
        Reel.objects.all().delete()
        _seed(n, owner)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get('/api/v1/reels/')
        assert response.status_code == 200
        assert len(_rows(response)) == n
        counts[n] = len(ctx.captured_queries)

    assert counts[20] == counts[5] == counts[1], (
        f'query count grew with rows: {counts}. A per-row query has come back -- '
        'check that get_comment_count and get_gift_count still read the '
        'annotation and the prefetch.'
    )


def test_feed_stays_under_the_query_ceiling_anonymously(owner):
    _seed(20, owner)
    client = APIClient()
    with CaptureQueriesContext(connection) as ctx:
        response = client.get('/api/v1/reels/')
    assert response.status_code == 200
    assert len(ctx.captured_queries) <= MAX_QUERIES_ANON, [
        q['sql'][:120] for q in ctx.captured_queries
    ]


def test_feed_stays_under_the_query_ceiling_when_authenticated(owner):
    _seed(20, owner)
    viewer = User.objects.create_user(username='budget_viewer', password='123456')
    client = APIClient()
    client.force_authenticate(user=viewer)
    with CaptureQueriesContext(connection) as ctx:
        response = client.get('/api/v1/reels/')
    assert response.status_code == 200
    assert len(ctx.captured_queries) <= MAX_QUERIES_AUTH, [
        q['sql'][:120] for q in ctx.captured_queries
    ]


def test_no_query_shape_repeats_once_per_row(owner):
    """The direct statement of the finding, independent of any ceiling."""
    import collections
    import re

    _seed(6, owner)
    client = APIClient()
    with CaptureQueriesContext(connection) as ctx:
        client.get('/api/v1/reels/')

    shapes = collections.Counter()
    for query in ctx.captured_queries:
        sql = re.sub(r'\b\d+\b', 'N', query['sql'])
        sql = re.sub(r"'[^']*'", "'X'", sql)
        shapes[sql] += 1

    per_row = {sql[:90]: n for sql, n in shapes.items() if n >= 6}
    assert not per_row, f'these ran once per row: {per_row}'


# ── the numbers are still right ──────────────────────────────────────────────


def test_comment_count_is_correct_when_annotated(owner):
    """The whole risk of reading an annotation instead of counting."""
    reel = _seed(1, owner)[0]
    for i in range(3):
        Comment.objects.create(reel=reel, user=owner, text=f'c{i}')

    client = APIClient()
    row = _rows(client.get('/api/v1/reels/'))[0]
    assert row['comment_count'] == 3


def test_comment_count_is_zero_with_no_comments(owner):
    _seed(1, owner)
    client = APIClient()
    assert _rows(client.get('/api/v1/reels/'))[0]['comment_count'] == 0


def test_comment_counts_are_not_shared_between_reels(owner):
    """A fan-out bug shows up here: every row getting the same total."""
    first, second = _seed(2, owner)
    Comment.objects.create(reel=first, user=owner, text='only on first')

    client = APIClient()
    by_id = {row['id']: row['comment_count'] for row in _rows(client.get('/api/v1/reels/'))}
    assert by_id[first.id] == 1
    assert by_id[second.id] == 0


def test_gift_count_sums_quantities_from_the_prefetch(owner):
    from api.models.gift import Gift, GiftTransaction

    reel = _seed(1, owner)[0]
    sender = User.objects.create_user(username='budget_sender', password='123456')
    gift = Gift.objects.create(name='Rose', coin_value=5, is_active=True)
    GiftTransaction.objects.create(
        sender=sender, recipient=owner, gift=gift, reel=reel, quantity=2, total_coins=10
    )
    GiftTransaction.objects.create(
        sender=sender, recipient=owner, gift=gift, reel=reel, quantity=3, total_coins=15
    )

    client = APIClient()
    row = _rows(client.get('/api/v1/reels/'))[0]
    assert row['gift_count'] == 5, 'quantities must be summed, not counted'


def test_gift_count_is_zero_with_no_gifts(owner):
    _seed(1, owner)
    client = APIClient()
    assert _rows(client.get('/api/v1/reels/'))[0]['gift_count'] == 0


def test_gift_counts_are_not_shared_between_reels(owner):
    from api.models.gift import Gift, GiftTransaction

    first, second = _seed(2, owner)
    sender = User.objects.create_user(username='budget_sender2', password='123456')
    gift = Gift.objects.create(name='Star', coin_value=5, is_active=True)
    GiftTransaction.objects.create(
        sender=sender, recipient=owner, gift=gift, reel=first, quantity=4, total_coins=20
    )

    client = APIClient()
    by_id = {row['id']: row['gift_count'] for row in _rows(client.get('/api/v1/reels/'))}
    assert by_id[first.id] == 4
    assert by_id[second.id] == 0


def test_the_unannotated_fallback_still_works(owner):
    """Other views serialise Reels without the feed's queryset."""
    from api.serializers.core import ReelSerializer

    reel = _seed(1, owner)[0]
    Comment.objects.create(reel=reel, user=owner, text='x')

    plain = Reel.objects.get(pk=reel.pk)  # no annotation, no prefetch
    data = ReelSerializer(plain).data
    assert data['comment_count'] == 1
    assert data['gift_count'] == 0
