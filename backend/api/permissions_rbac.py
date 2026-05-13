"""
RBAC (Role-Based Access Control) Permission Classes

This module provides Django REST Framework permission classes for enforcing
role-based access control on API endpoints.
"""
from rest_framework import permissions
from .models_rbac import Role, Permission, RolePermission


class HasRolePermission(permissions.BasePermission):
    """
    Permission class to check if a user has a specific permission.
    
    Usage:
    class MyView(APIView):
        permission_classes = [HasRolePermission]
        required_permission = 'content.flip.upload'
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superuser always has access
        if request.user.is_superuser:
            return True
        
        # Get the required permission from the view
        required_permission = getattr(view, 'required_permission', None)
        if not required_permission:
            return False
        
        # Get the user's role
        if not hasattr(request.user, 'profile') or not request.user.profile.role:
            return False
        
        role = request.user.profile.role
        
        # Check if the role has the required permission with full or read-only access
        try:
            role_permission = RolePermission.objects.get(
                role=role,
                permission__id=required_permission
            )
            return role_permission.access_level in ['full', 'read_only']
        except RolePermission.DoesNotExist:
            return False
    
    def has_object_permission(self, request, view, obj):
        # For object-level permissions, we can check if the user owns the object
        # This can be customized based on the object type
        if request.user.is_superuser:
            return True
        
        # If the object has a user field, check if it's the current user
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        # If the object is the user itself
        if obj == request.user:
            return True
        
        return False


class IsSuperAdmin(permissions.BasePermission):
    """
    Permission class to check if the user is a Super Admin.
    
    Super Admin has full access to all permissions.
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user is superuser
        if request.user.is_superuser:
            return True
        
        # Check if user has superadmin role
        if hasattr(request.user, 'profile') and request.user.profile.role:
            return request.user.profile.role.id == 'superadmin'
        
        return False


class IsInternalOperator(permissions.BasePermission):
    """
    Permission class to check if the user is an internal operator (admin staff).
    
    Internal operators are users with is_staff=True or have an internal operator role.
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user is superuser
        if request.user.is_superuser:
            return True
        
        # Check if user is staff
        if request.user.is_staff:
            return True
        
        # Check if user has an internal operator role
        if hasattr(request.user, 'profile') and request.user.profile.role:
            return request.user.profile.role.type == 'internal_operator'
        
        return False


class IsPlatformUser(permissions.BasePermission):
    """
    Permission class to check if the user is a platform user (regular user).
    
    Platform users are users with is_staff=False and have a platform user role.
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Check if user is staff (internal operator)
        if request.user.is_staff:
            return False
        
        # Check if user has a platform user role
        if hasattr(request.user, 'profile') and request.user.profile.role:
            return request.user.profile.role.type == 'platform_user'
        
        return True


class HasAnyPermission(permissions.BasePermission):
    """
    Permission class to check if a user has ANY of the specified permissions.
    
    Usage:
    class MyView(APIView):
        permission_classes = [HasAnyPermission]
        required_permissions = ['content.flip.upload', 'content.flip.delete.own']
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superuser always has access
        if request.user.is_superuser:
            return True
        
        # Get the required permissions from the view
        required_permissions = getattr(view, 'required_permissions', [])
        if not required_permissions:
            return False
        
        # Get the user's role
        if not hasattr(request.user, 'profile') or not request.user.profile.role:
            return False
        
        role = request.user.profile.role
        
        # Check if the role has ANY of the required permissions
        role_permissions = RolePermission.objects.filter(
            role=role,
            permission__id__in=required_permissions,
            access_level__in=['full', 'read_only']
        )
        
        return role_permissions.exists()


class HasAllPermissions(permissions.BasePermission):
    """
    Permission class to check if a user has ALL of the specified permissions.
    
    Usage:
    class MyView(APIView):
        permission_classes = [HasAllPermissions]
        required_permissions = ['content.flip.upload', 'campaign.enter']
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superuser always has access
        if request.user.is_superuser:
            return True
        
        # Get the required permissions from the view
        required_permissions = getattr(view, 'required_permissions', [])
        if not required_permissions:
            return False
        
        # Get the user's role
        if not hasattr(request.user, 'profile') or not request.user.profile.role:
            return False
        
        role = request.user.profile.role
        
        # Check if the role has ALL of the required permissions
        role_permissions_count = RolePermission.objects.filter(
            role=role,
            permission__id__in=required_permissions,
            access_level__in=['full', 'read_only']
        ).count()
        
        return role_permissions_count == len(required_permissions)
