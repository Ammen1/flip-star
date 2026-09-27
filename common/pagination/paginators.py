"""
Reusable paginators.

The codebase currently hand-rolls offset pagination in several places
(``wallet_transactions``, ``my_withdrawals``, the admin lists), each computing
``count``/``page``/``has_next`` itself. :class:`StandardResultsPagination`
reproduces that exact response shape so those views can adopt it without
changing their contract.

:class:`CursorResultsPagination` is provided for new endpoints over large,
append-only tables (``CoinTransaction``, ``Notification``) where offset
pagination degrades linearly -- see audit section 09.

:class:`OptInPageNumberPagination` is the global default. It exists because
enabling ordinary DRF pagination across this project would have been a breaking
change -- see its docstring for the two call sites that proved it.
"""

from __future__ import annotations

from collections import OrderedDict

from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

#: Rows returned to a client that asks for no pagination at all. Bounds the
#: response without changing its shape. Overridable per view via
#: ``max_unpaginated_results``.
MAX_UNPAGINATED_RESULTS = 100


class StandardResultsPagination(PageNumberPagination):
    """Offset pagination matching the shape the existing wallet views return."""

    page_size = DEFAULT_PAGE_SIZE
    page_size_query_param = 'page_size'
    max_page_size = MAX_PAGE_SIZE

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ('count', self.page.paginator.count),
                    ('page', self.page.number),
                    ('page_size', self.get_page_size(self.request)),
                    ('has_next', self.page.has_next()),
                    ('has_prev', self.page.has_previous()),
                    ('results', data),
                ]
            )
        )


class CursorResultsPagination(CursorPagination):
    """Keyset pagination for large, time-ordered tables."""

    page_size = DEFAULT_PAGE_SIZE
    page_size_query_param = 'page_size'
    max_page_size = MAX_PAGE_SIZE
    ordering = '-created_at'


class OptInPageNumberPagination(StandardResultsPagination):
    """Bound every list response without changing the shape existing clients see.

    Why this exists rather than plain :class:`StandardResultsPagination` as the
    global default: before this project had any paginator, 41 GET-list routes
    returned whole tables, and the clients were written against a bare JSON
    array. Switching them to an envelope breaks callers that index the response
    directly. Two were found in the web app alone:

        Flipstar-web/pages/general/LandingPage.jsx
            setPosts(data.slice(0, 6))
            -- an object has no .slice: TypeError, the page fails to render.

        Flipstar-web/pages/general/NotificationsPage.jsx
            transform(Array.isArray(data) ? data : [])
            -- an envelope is not an Array, so the list silently renders empty.

    The mobile app is out of scope for this change and cannot be surveyed from
    here, which is the other reason the default has to stay compatible.

    So the contract is:

    * The request asks for pagination -- ``?page=`` or ``?page_size=`` present --
      and gets the ``{count, page, page_size, has_next, has_prev, results}``
      envelope, the same shape the hand-rolled wallet and admin lists already
      return.
    * The request asks for nothing and gets a plain JSON array, exactly as
      before, capped at ``max_unpaginated_results`` rows.

    The cap is what closes the finding: a response can no longer grow with the
    size of a table. It is a real behaviour change -- a client that never
    paginates and has more than the cap now sees a prefix rather than
    everything -- so truncation is advertised rather than silent:

        X-Result-Truncated: true
        X-Result-Limit: 100

    Only those two headers, and only when truncation actually happened. No row
    count is emitted: most of these endpoints are end-to-end encrypted, and a
    plaintext header carrying "this user has N items" would leak volume metadata
    the sealed body is there to protect. "There is more than 100" is the minimum
    a client needs in order to know it must start paginating.

    Ordering note: an unordered queryset makes any limit arbitrary, and slicing
    one is what produces Django's UnorderedObjectListWarning. Every model behind
    the routes this bounds declares ``Meta.ordering``; a view whose queryset does
    not should add ``order_by`` rather than rely on insertion order.
    """

    max_unpaginated_results = MAX_UNPAGINATED_RESULTS

    def _opted_in(self, request) -> bool:
        params = request.query_params
        return self.page_query_param in params or (
            self.page_size_query_param is not None and self.page_size_query_param in params
        )

    def paginate_queryset(self, queryset, request, view=None):
        self._is_paginated = self._opted_in(request)
        if self._is_paginated:
            return super().paginate_queryset(queryset, request, view)

        # Unpaginated: hand back a bounded prefix. Fetching cap + 1 rows is how
        # "is there more?" is answered without a COUNT(*) over the whole table,
        # which would defeat the point of bounding the work.
        self._cap = int(getattr(view, 'max_unpaginated_results', self.max_unpaginated_results))
        window = list(queryset[: self._cap + 1])
        self._truncated = len(window) > self._cap
        return window[: self._cap]

    def get_paginated_response(self, data):
        if getattr(self, '_is_paginated', False):
            return super().get_paginated_response(data)

        response = Response(data)
        if getattr(self, '_truncated', False):
            response['X-Result-Truncated'] = 'true'
            response['X-Result-Limit'] = str(self._cap)
        return response
