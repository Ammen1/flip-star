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
"""

from __future__ import annotations

from collections import OrderedDict

from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


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
