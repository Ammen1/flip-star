"""
Reusable DRF permission classes.

The codebase currently expresses authorization three different ways: the
``IsAdminUser`` class, inline ``request.user.is_staff`` checks, and a private
``_is_admin`` helper on one viewset. These classes give those the same name so
new code has one obvious choice; existing call sites are left untouched.
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsStaff(BasePermission):
    """Django staff flag. Equivalent to DRF's ``IsAdminUser``, named for intent."""

    message = 'Staff access is required.'

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)


class IsSuperUser(BasePermission):
    """Full administrative access. Use for destructive operations."""

    message = 'Superuser access is required.'

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)


class IsOwner(BasePermission):
    """
    Object-level ownership.

    Expects the object to expose a ``user`` attribute. Views over models that
    name the field differently should subclass and override ``owner_field``.
    """

    message = 'You do not own this resource.'
    owner_field = 'user'

    def has_object_permission(self, request, view, obj) -> bool:
        owner = getattr(obj, self.owner_field, None)
        return owner is not None and owner == request.user


class IsOwnerOrReadOnly(IsOwner):
    """Anyone authenticated may read; only the owner may modify."""

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return super().has_object_permission(request, view, obj)


class IsOwnerOrStaff(IsOwner):
    """The owner, or any staff member."""

    def has_object_permission(self, request, view, obj) -> bool:
        if request.user and request.user.is_staff:
            return True
        return super().has_object_permission(request, view, obj)


class IsOwnerOrStaffOrReadOnly(IsOwnerOrStaff):
    """
    Safe methods (GET/HEAD/OPTIONS) open to anyone; write methods require
    an authenticated user who is the object's owner or staff.

    Intended as a ViewSet's class-level default ``permission_classes`` for
    a publicly-readable resource with per-owner write access -- e.g.
    ``ReelViewSet``/``CommentViewSet``/``CommentReplyViewSet``/``SavedPostViewSet``,
    which were previously ``AllowAny`` at the class level with no override
    for write operations. Any action not otherwise covered by a
    ``get_permissions()`` override (a new @action added later, for
    instance) falls through to this and is rejected rather than silently
    allowed -- fails closed by default instead of requiring every future
    action to remember its own check.
    """

    message = 'You must be the owner or staff to modify this resource.'

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return super().has_object_permission(request, view, obj)


class HasAdminPermission(BasePermission):
    """
    Per-action admin authorization against the requesting user's AdminRole,
    not just the ``is_staff`` flag.

    Set ``required_permission = '<permission-string>'`` (matching
    ``AdminRole.PERMISSION_CHOICES``, e.g. 'view_users', 'edit_users',
    'delete_users', 'moderate_content', 'manage_admins') as a class
    attribute on the view. Superusers always pass. A view with no
    ``required_permission`` set falls back to the plain ``is_staff`` check
    -- the same coarse behavior as ``IsAdminUser`` -- so adding this class
    without also setting ``required_permission`` is a no-op, not a
    tightening; every admin view that should be permission-scoped needs
    the attribute set explicitly.

    Without this, any ``is_staff=True`` account has full access to every
    admin endpoint regardless of what their AdminRole actually grants --
    the AdminRole configuration becomes decorative.
    """

    message = 'You do not have the required admin permission for this action.'

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        required_permission = getattr(view, 'required_permission', None)
        if not required_permission:
            return bool(user.is_staff)

        from api.models.subscription import AdminRole

        try:
            admin_role = AdminRole.objects.get(user=user)
        except AdminRole.DoesNotExist:
            return False
        return admin_role.has_permission(required_permission)
