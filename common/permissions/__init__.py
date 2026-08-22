"""Reusable DRF permission classes."""

from common.permissions.roles import (
    HasAdminPermission,
    IsOwner,
    IsOwnerOrReadOnly,
    IsOwnerOrStaff,
    IsOwnerOrStaffOrReadOnly,
    IsStaff,
    IsSuperUser,
)

__all__ = [
    'HasAdminPermission',
    'IsOwner', 'IsOwnerOrReadOnly', 'IsOwnerOrStaff', 'IsOwnerOrStaffOrReadOnly',
    'IsStaff', 'IsSuperUser',
]
