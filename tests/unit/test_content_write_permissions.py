"""
Regression tests for a fix ported from `master`: ReelViewSet, CommentViewSet,
and CommentReplyViewSet were registered with `permission_classes = [AllowAny]`
and never overrode it at the class level, so any action not explicitly listed
in their get_permissions() overrides (e.g. ReelViewSet.save, the bookmark
toggle) fell through to fully open access. An anonymous POST to
/reels/<pk>/save/ reached `SavedPost.objects.get_or_create(user=AnonymousUser,
...)` unguarded -- an unhandled error, not a clean rejection.

common.permissions.IsOwnerOrStaffOrReadOnly (api/views/core.py,
api/views/extended.py) is now each ViewSet's class-level default: safe
methods stay open to anyone, write methods require authentication, and
object-level access additionally requires ownership or staff. No database
needed -- has_permission() alone (no object involved) is what rejects an
anonymous write, before get_object() is ever called.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from rest_framework.permissions import SAFE_METHODS
from rest_framework.test import APIRequestFactory

from api.views.core import ReelViewSet
from common.permissions import IsOwnerOrStaffOrReadOnly

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# The concrete regression: ReelViewSet.save, anonymous
# ---------------------------------------------------------------------------

def test_anonymous_reel_save_is_rejected_before_reaching_the_database():
    """The exact gap the audit found: 'save' isn't in ReelViewSet's
    get_permissions() allowlist, so before this fix it fell through to the
    class-level AllowAny default. Now it falls through to
    IsOwnerOrStaffOrReadOnly instead, which rejects an unauthenticated
    write at has_permission() -- before get_object() ever runs, so this
    needs no real Reel row to prove."""
    factory = APIRequestFactory()
    view = ReelViewSet.as_view({'post': 'save'})
    request = factory.post('/api/reels/00000000-0000-0000-0000-000000000000/save/')

    response = view(request, pk='00000000-0000-0000-0000-000000000000')

    assert response.status_code in (401, 403), response.data


def test_anonymous_reel_list_is_still_open():
    """Reads must remain public -- this fix must not accidentally lock
    down browsing."""
    factory = APIRequestFactory()
    view = ReelViewSet.as_view({'get': 'list'})
    request = factory.get('/api/reels/')

    response = view(request)

    assert response.status_code == 200, response.data


# ---------------------------------------------------------------------------
# IsOwnerOrStaffOrReadOnly in isolation
# ---------------------------------------------------------------------------

def _request(method, user=None):
    req = MagicMock()
    req.method = method
    req.user = user
    return req


def test_safe_methods_open_to_anyone():
    perm = IsOwnerOrStaffOrReadOnly()
    for method in SAFE_METHODS:
        assert perm.has_permission(_request(method, user=None), view=None) is True


def test_unsafe_methods_require_authentication():
    perm = IsOwnerOrStaffOrReadOnly()
    anon = MagicMock(is_authenticated=False)
    assert perm.has_permission(_request('POST', user=anon), view=None) is False

    auth = MagicMock(is_authenticated=True)
    assert perm.has_permission(_request('POST', user=auth), view=None) is True


def test_object_permission_requires_ownership_or_staff():
    perm = IsOwnerOrStaffOrReadOnly()
    owner = MagicMock(is_staff=False)
    other_user = MagicMock(is_staff=False)
    staff_user = MagicMock(is_staff=True)
    obj = MagicMock(user=owner)

    assert perm.has_object_permission(_request('DELETE', user=owner), view=None, obj=obj) is True
    assert perm.has_object_permission(_request('DELETE', user=other_user), view=None, obj=obj) is False
    assert perm.has_object_permission(_request('DELETE', user=staff_user), view=None, obj=obj) is True


def test_object_permission_safe_methods_bypass_ownership():
    perm = IsOwnerOrStaffOrReadOnly()
    other_user = MagicMock(is_staff=False)
    obj = MagicMock(user=MagicMock())

    for method in SAFE_METHODS:
        assert perm.has_object_permission(_request(method, user=other_user), view=None, obj=obj) is True
