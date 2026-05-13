"""
RBAC (Role-Based Access Control) Serializers

This module provides serializers for the RBAC models:
- RoleSerializer
- PermissionSerializer
- RolePermissionSerializer
- AuditLogSerializer
- UserRoleSerializer
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models_rbac import Role, Permission, RolePermission, AuditLog


class RoleSerializer(serializers.ModelSerializer):
    """Serializer for Role model with full CRUD support"""
    user_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Role
        fields = [
            'id', 'name', 'description', 'type', 'surfaces',
            'is_default', 'is_active', 'created_at', 'updated_at',
            'user_count',
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_user_count(self, obj):
        """Get the number of users with this role"""
        return obj.get_user_count()


class PermissionSerializer(serializers.ModelSerializer):
    """Serializer for Permission model with full CRUD support"""
    class Meta:
        model = Permission
        fields = [
            'id', 'domain', 'name', 'description',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class RolePermissionSerializer(serializers.ModelSerializer):
    """Serializer for RolePermission model with full CRUD support"""
    role_name = serializers.CharField(source='role.name', read_only=True)
    permission_name = serializers.CharField(source='permission.name', read_only=True)
    permission_domain = serializers.CharField(source='permission.domain', read_only=True)
    
    class Meta:
        model = RolePermission
        fields = [
            'id', 'role', 'role_name', 'permission', 'permission_name',
            'permission_domain', 'access_level', 'conditions',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer for AuditLog model (read-only)"""
    actor_username = serializers.CharField(source='actor.username', read_only=True)
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'actor', 'actor_username', 'action', 'target_type',
            'target_id', 'target_name', 'old_value', 'new_value',
            'ip_address', 'user_agent', 'timestamp',
        ]
        read_only_fields = [
            'id', 'actor', 'action', 'target_type', 'target_id',
            'target_name', 'old_value', 'new_value', 'ip_address',
            'user_agent', 'timestamp',
        ]


class UserRoleSerializer(serializers.ModelSerializer):
    """Serializer for User with Role information"""
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    role_id = serializers.CharField(source='profile.role.id', read_only=True)
    role_name = serializers.CharField(source='profile.role.name', read_only=True)
    role_type = serializers.CharField(source='profile.role.type', read_only=True)
    is_staff = serializers.BooleanField(source='profile.is_staff', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'role_id', 'role_name', 'role_type', 'is_staff',
        ]
        read_only_fields = ['id', 'username', 'email', 'role_id', 'role_name', 'role_type', 'is_staff']
