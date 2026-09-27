"""Audit C-01: list responses are bounded, and the legacy shape is preserved.

The whole point of OptInPageNumberPagination is that it does two contradictory
things at once -- bound the response, and not change what an existing client
sees. These tests pin both halves, plus the boundary between them, because a
future "let's just use PageNumberPagination" would silently break the clients
named in the paginator's docstring.
"""

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from rest_framework.generics import ListAPIView
from rest_framework.serializers import ModelSerializer
from rest_framework.test import APIClient

from api.models import Reel
from common.pagination import OptInPageNumberPagination
from common.pagination.paginators import MAX_UNPAGINATED_RESULTS

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class _ReelStub(ModelSerializer):
    class Meta:
        model = Reel
        fields = ['id']


class _ReelList(ListAPIView):
    queryset = Reel.objects.all().order_by('id')
    serializer_class = _ReelStub
    permission_classes = []
    authentication_classes = []


class _SmallCapReelList(_ReelList):
    max_unpaginated_results = 3


def _make_reels(n, *, owner=None):
    owner = owner or User.objects.create_user(username='pag_owner', password='x')
    return [Reel.objects.create(user=owner, caption='r%d' % i) for i in range(n)]


def _get(view_cls, query=''):
    request = RequestFactory().get('/x/' + query)
    return view_cls.as_view()(request)


# ── the legacy contract: no pagination asked for, bare array returned ────────


def test_unpaginated_request_still_returns_a_bare_array():
    _make_reels(3)
    response = _get(_ReelList)
    assert response.status_code == 200
    assert isinstance(response.data, list), (
        'a client that does not ask for pagination must still get an array; '
        'an envelope here breaks LandingPage.jsx and NotificationsPage.jsx'
    )
    assert len(response.data) == 3


def test_empty_unpaginated_request_returns_an_empty_array_not_an_envelope():
    response = _get(_ReelList)
    assert response.status_code == 200
    assert response.data == []


def test_unpaginated_response_sets_no_truncation_headers_when_nothing_was_cut():
    _make_reels(3)
    response = _get(_ReelList)
    assert 'X-Result-Truncated' not in response
    assert 'X-Result-Limit' not in response


# ── the new contract: the response is bounded ────────────────────────────────


def test_unpaginated_response_is_capped():
    _make_reels(5)
    response = _get(_SmallCapReelList)
    assert isinstance(response.data, list)
    assert len(response.data) == 3, 'the per-view cap must bound the response'


def test_truncation_is_advertised_rather_than_silent():
    _make_reels(5)
    response = _get(_SmallCapReelList)
    assert response['X-Result-Truncated'] == 'true'
    assert response['X-Result-Limit'] == '3'


def test_exactly_at_the_cap_is_not_reported_as_truncated():
    """The cap+1 fetch must not report truncation for a list that just fits."""
    _make_reels(3)
    response = _get(_SmallCapReelList)
    assert len(response.data) == 3
    assert 'X-Result-Truncated' not in response


def test_no_row_count_leaks_into_plaintext_headers():
    """Most of these endpoints are E2E encrypted; volume metadata stays sealed."""
    _make_reels(5)
    response = _get(_SmallCapReelList)
    header_blob = ' '.join(f'{k}:{v}' for k, v in response.items()).lower()
    assert 'result-count' not in header_blob
    assert '5' not in response.get('X-Result-Limit', '')


# ── opting in ────────────────────────────────────────────────────────────────


def test_page_param_returns_the_envelope():
    _make_reels(5)
    response = _get(_ReelList, '?page=1&page_size=2')
    assert set(response.data) >= {'count', 'page', 'page_size', 'has_next', 'has_prev', 'results'}
    assert response.data['count'] == 5
    assert response.data['page'] == 1
    assert response.data['page_size'] == 2
    assert response.data['has_next'] is True
    assert response.data['has_prev'] is False
    assert len(response.data['results']) == 2


def test_page_size_alone_also_opts_in():
    _make_reels(5)
    response = _get(_ReelList, '?page_size=2')
    assert isinstance(response.data, dict)
    assert len(response.data['results']) == 2


def test_second_page_reports_has_prev():
    _make_reels(5)
    response = _get(_ReelList, '?page=2&page_size=2')
    assert response.data['page'] == 2
    assert response.data['has_prev'] is True


def test_paginated_pages_do_not_overlap_or_skip():
    _make_reels(5)
    first = _get(_ReelList, '?page=1&page_size=2').data['results']
    second = _get(_ReelList, '?page=2&page_size=2').data['results']
    third = _get(_ReelList, '?page=3&page_size=2').data['results']
    ids = [row['id'] for row in first + second + third]
    assert len(ids) == 5
    assert len(set(ids)) == 5, 'pages overlapped'


def test_page_size_cannot_exceed_max_page_size():
    _make_reels(3)
    response = _get(_ReelList, '?page_size=100000')
    assert response.data['page_size'] <= OptInPageNumberPagination.max_page_size


# ── the default cap is a real bound, not a large number ──────────────────────


def test_default_cap_is_bounded_and_modest():
    assert MAX_UNPAGINATED_RESULTS == 100
    assert OptInPageNumberPagination.max_unpaginated_results == MAX_UNPAGINATED_RESULTS


def test_capping_does_not_issue_a_count_query(django_assert_num_queries):
    """cap + 1 rows answers 'is there more?'; a COUNT(*) would defeat the point."""
    _make_reels(5)
    with django_assert_num_queries(1):
        _get(_SmallCapReelList)


# ── end to end, through a real endpoint ──────────────────────────────────────
#
# Everything above drives a stub ListAPIView with a cap of 3, which pins the
# paginator's logic but not the wiring. These two go through /api/v1/reels/ with
# the real global default, because "the paginator works" and "the endpoint is
# bounded" are different claims.


def _seed_reels(n, owner):
    return Reel.objects.bulk_create(
        [Reel(user=owner, caption=f'r{i}', processed=True) for i in range(n)]
    )


def test_a_real_endpoint_caps_at_the_global_default_and_advertises_it():
    owner = User.objects.create_user(username='cap_owner', password='123456')
    _seed_reels(MAX_UNPAGINATED_RESULTS + 5, owner)

    response = APIClient().get('/api/v1/reels/')
    assert response.status_code == 200
    body = response.json()

    assert isinstance(body, list), 'unpaginated callers must still get a bare array'
    assert len(body) == MAX_UNPAGINATED_RESULTS
    assert response['X-Result-Truncated'] == 'true'
    assert response['X-Result-Limit'] == str(MAX_UNPAGINATED_RESULTS)


def test_the_envelope_reports_the_true_total_not_the_cap():
    """A client that pages must be able to see how much there really is."""
    owner = User.objects.create_user(username='cap_owner2', password='123456')
    total = MAX_UNPAGINATED_RESULTS + 5
    _seed_reels(total, owner)

    response = APIClient().get('/api/v1/reels/?page=2&page_size=50')
    assert response.status_code == 200
    body = response.json()

    assert body['count'] == total
    assert len(body['results']) == 50
    assert body['has_prev'] is True
    assert body['has_next'] is True
