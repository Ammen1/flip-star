"""
RBAC (Role-Based Access Control) API Views

This module provides API endpoints for managing roles, permissions,
role-permission mappings, and audit logs for the FlipStar RBAC system.
"""
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth.models import User
from .models_rbac import Role, Permission, RolePermission, AuditLog
from .serializers_rbac import (
    RoleSerializer, PermissionSerializer, RolePermissionSerializer,
    AuditLogSerializer, UserRoleSerializer
)
from .permissions_rbac import IsSuperAdmin, HasRolePermission


class RoleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Role management with full CRUD operations.
    
    Endpoints:
    - GET    /api/admin/rbac/roles/              - List all roles
    - POST   /api/admin/rbac/roles/              - Create new role
    - GET    /api/admin/rbac/roles/{id}/         - Get role details
    - PUT    /api/admin/rbac/roles/{id}/         - Update role
    - PATCH  /api/admin/rbac/roles/{id}/         - Partial update role
    - DELETE /api/admin/rbac/roles/{id}/         - Delete role
    """
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsSuperAdmin]  # Only Super Admin can manage roles
    required_permission = 'admin.role.assign'
    
    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by type if provided
        role_type = self.request.query_params.get('type')
        if role_type:
            queryset = queryset.filter(type=role_type)
        # Filter by active status if provided
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        return queryset
    
    def perform_create(self, serializer):
        # Set created_by to the current user
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        # Set updated_by to the current user
        serializer.save(updated_by=self.request.user)
    
    def get_client_ip(self):
        """Get the client IP address from the request"""
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = self.request.META.get('REMOTE_ADDR')
        return ip
    
    def perform_destroy(self, instance):
        # Log the deletion
        AuditLog.objects.create(
            actor=self.request.user,
            action='role_delete',
            target_type='role',
            target_id=instance.id,
            target_name=instance.name,
            old_value={'name': instance.name, 'description': instance.description},
            ip_address=self.get_client_ip(),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
        )
        instance.delete()
    
    @action(detail=True, methods=['get'])
    def permissions(self, request, pk=None):
        """Get all permissions for a specific role"""
        role = self.get_object()
        role_permissions = RolePermission.objects.filter(role=role)
        serializer = RolePermissionSerializer(role_permissions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def users(self, request, pk=None):
        """Get all users with this role"""
        role = self.get_object()
        users = role.users.all()
        serializer = UserRoleSerializer(users, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def set_default(self, request):
        """Set a role as the default for new users"""
        role_id = request.data.get('role_id')
        if not role_id:
            return Response(
                {'error': 'role_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Remove default from all roles
            Role.objects.update(is_default=False)
            
            # Set new default
            role = Role.objects.get(id=role_id)
            role.is_default = True
            role.save()
            
            # Log the action
            AuditLog.objects.create(
                actor=request.user,
                action='role_update',
                target_type='role',
                target_id=role.id,
                target_name=role.name,
                old_value={'is_default': False},
                new_value={'is_default': True},
                ip_address=self.get_client_ip(),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
            
            serializer = self.get_serializer(role)
            return Response(serializer.data)
        except Role.DoesNotExist:
            return Response(
                {'error': 'Role not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def get_client_ip(self):
        """Get the client IP address from the request"""
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = self.request.META.get('REMOTE_ADDR')
        return ip


class PermissionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Permission management with full CRUD operations.
    
    Endpoints:
    - GET    /api/admin/rbac/permissions/          - List all permissions
    - POST   /api/admin/rbac/permissions/          - Create new permission
    - GET    /api/admin/rbac/permissions/{id}/     - Get permission details
    - PUT    /api/admin/rbac/permissions/{id}/     - Update permission
    - PATCH  /api/admin/rbac/permissions/{id}/     - Partial update permission
    - DELETE /api/admin/rbac/permissions/{id}/     - Delete permission
    """
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsSuperAdmin]  # Only Super Admin can manage permissions
    required_permission = 'admin.role.assign'
    
    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by domain if provided
        domain = self.request.query_params.get('domain')
        if domain:
            queryset = queryset.filter(domain=domain)
        # Filter by active status if provided
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        return queryset
    
    def perform_create(self, serializer):
        # Set created_by to the current user
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        # Set updated_by to the current user
        serializer.save(updated_by=self.request.user)
    
    def perform_destroy(self, instance):
        # Log the deletion
        AuditLog.objects.create(
            actor=self.request.user,
            action='permission_delete',
            target_type='permission',
            target_id=instance.id,
            target_name=instance.name,
            old_value={'id': instance.id, 'name': instance.name},
            ip_address=self.get_client_ip(),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
        )
        instance.delete()
    
    @action(detail=True, methods=['get'])
    def roles(self, request, pk=None):
        """Get all roles that have this permission"""
        permission = self.get_object()
        role_permissions = RolePermission.objects.filter(permission=permission)
        roles = [rp.role for rp in role_permissions]
        serializer = RoleSerializer(roles, many=True)
        return Response(serializer.data)
    
    def get_client_ip(self):
        """Get the client IP address from the request"""
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = self.request.META.get('REMOTE_ADDR')
        return ip


class RolePermissionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for RolePermission management with full CRUD operations.
    
    Endpoints:
    - GET    /api/admin/rbac/role-permissions/        - List all role-permission mappings
    - POST   /api/admin/rbac/role-permissions/        - Create role-permission mapping
    - GET    /api/admin/rbac/role-permissions/{id}/   - Get role-permission details
    - PUT    /api/admin/rbac/role-permissions/{id}/   - Update role-permission mapping
    - PATCH  /api/admin/rbac/role-permissions/{id}/   - Partial update role-permission mapping
    - DELETE /api/admin/rbac/role-permissions/{id}/   - Delete role-permission mapping
    """
    queryset = RolePermission.objects.all()
    serializer_class = RolePermissionSerializer
    permission_classes = [IsSuperAdmin]  # Only Super Admin can manage role-permission mappings
    required_permission = 'admin.role.assign'
    
    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by role if provided
        role_id = self.request.query_params.get('role_id')
        if role_id:
            queryset = queryset.filter(role_id=role_id)
        # Filter by permission if provided
        permission_id = self.request.query_params.get('permission_id')
        if permission_id:
            queryset = queryset.filter(permission_id=permission_id)
        # Filter by access level if provided
        access_level = self.request.query_params.get('access_level')
        if access_level:
            queryset = queryset.filter(access_level=access_level)
        return queryset
    
    def perform_create(self, serializer):
        # Set created_by to the current user
        serializer.save(created_by=self.request.user)
        
        # Log the action
        role_permission = serializer.instance
        AuditLog.objects.create(
            actor=self.request.user,
            action='permission_grant',
            target_type='role_permission',
            target_id=str(role_permission.id),
            target_name=f'{role_permission.role.name} - {role_permission.permission.name}',
            new_value={
                'role': role_permission.role.id,
                'permission': role_permission.permission.id,
                'access_level': role_permission.access_level,
            },
            ip_address=self.get_client_ip(),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
        )
    
    def perform_update(self, serializer):
        # Get old value for logging
        old_instance = self.get_object()
        old_value = {
            'role': old_instance.role.id,
            'permission': old_instance.permission.id,
            'access_level': old_instance.access_level,
        }
        
        # Set updated_by to the current user
        serializer.save(updated_by=self.request.user)
        
        # Log the action
        role_permission = serializer.instance
        AuditLog.objects.create(
            actor=self.request.user,
            action='role_permission_update',
            target_type='role_permission',
            target_id=str(role_permission.id),
            target_name=f'{role_permission.role.name} - {role_permission.permission.name}',
            old_value=old_value,
            new_value={
                'role': role_permission.role.id,
                'permission': role_permission.permission.id,
                'access_level': role_permission.access_level,
            },
            ip_address=self.get_client_ip(),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
        )
    
    def perform_destroy(self, instance):
        # Log the action
        AuditLog.objects.create(
            actor=self.request.user,
            action='permission_revoke',
            target_type='role_permission',
            target_id=str(instance.id),
            target_name=f'{instance.role.name} - {instance.permission.name}',
            old_value={
                'role': instance.role.id,
                'permission': instance.permission.id,
                'access_level': instance.access_level,
            },
            ip_address=self.get_client_ip(),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
        )
        instance.delete()
    
    @action(detail=False, methods=['post'])
    def bulk_assign(self, request):
        """Bulk assign permissions to a role"""
        role_id = request.data.get('role_id')
        permission_ids = request.data.get('permission_ids', [])
        access_level = request.data.get('access_level', 'full')
        
        if not role_id:
            return Response(
                {'error': 'role_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            role = Role.objects.get(id=role_id)
            created_count = 0
            updated_count = 0
            
            for perm_id in permission_ids:
                permission = Permission.objects.get(id=perm_id)
                role_perm, created = RolePermission.objects.update_or_create(
                    role=role,
                    permission=permission,
                    defaults={
                        'access_level': access_level,
                        'created_by': request.user,
                        'updated_by': request.user,
                    }
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
            
            return Response({
                'message': f'Created {created_count}, updated {updated_count} role-permission mappings',
                'created': created_count,
                'updated': updated_count,
            })
        except Role.DoesNotExist:
            return Response(
                {'error': 'Role not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Permission.DoesNotExist:
            return Response(
                {'error': 'One or more permissions not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def get_client_ip(self):
        """Get the client IP address from the request"""
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = self.request.META.get('REMOTE_ADDR')
        return ip


class UserRoleViewSet(viewsets.ViewSet):
    """
    ViewSet for User Role Assignment.
    
    Endpoints:
    - GET    /api/admin/rbac/users/                - List all users with roles
    - GET    /api/admin/rbac/users/{user_id}/role/ - Get user's role
    - PUT    /api/admin/rbac/users/{user_id}/role/ - Assign/change user role
    - POST   /api/admin/rbac/users/bulk-assign/     - Bulk assign roles to users
    """
    permission_classes = [IsSuperAdmin]  # Only Super Admin can assign roles
    required_permission = 'admin.role.assign'
    
    def list(self, request):
        """List all users with their roles"""
        users = User.objects.prefetch_related('profile__roles').all()
        serializer = UserRoleSerializer(users, many=True)
        return Response(serializer.data)
    
    def retrieve(self, request, pk=None):
        """Get a user's role"""
        try:
            user = User.objects.get(id=pk)
            serializer = UserRoleSerializer(user)
            return Response(serializer.data)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def update(self, request, pk=None):
        """Assign or change a user's roles and credentials (supports multiple roles)"""
        try:
            user = User.objects.get(id=pk)
            role_ids = request.data.get('role_ids', [])
            email = request.data.get('email')
            password = request.data.get('password')
            
            # Get current roles
            old_role_ids = list(user.profile.roles.values_list('id', flat=True))
            
            # Clear existing roles and add new ones
            user.profile.roles.clear()
            for role_id in role_ids:
                try:
                    role = Role.objects.get(id=role_id)
                    user.profile.roles.add(role)
                except Role.DoesNotExist:
                    continue
            
            # Update is_staff based on role types (if any role is internal_operator, user is staff)
            has_internal_role = user.profile.roles.filter(type='internal_operator').exists()
            user.profile.is_staff = has_internal_role
            user.is_staff = has_internal_role
            user.profile.save()
            user.save()
            
            # Update email if provided
            if email:
                user.email = email
                user.save()
            
            # Update password if provided
            if password:
                user.set_password(password)
                user.save()
            
            # Log the action
            AuditLog.objects.create(
                actor=request.user,
                action='role_assign' if set(old_role_ids) != set(role_ids) else 'role_update',
                target_type='user',
                target_id=str(user.id),
                target_name=user.username,
                old_value={'roles': old_role_ids},
                new_value={'roles': role_ids, 'email_updated': bool(email), 'password_updated': bool(password)},
                ip_address=self.get_client_ip(),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
            
            serializer = UserRoleSerializer(user)
            return Response(serializer.data)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Role.DoesNotExist:
            return Response(
                {'error': 'Role not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'])
    def bulk_assign(self, request):
        """Bulk assign roles to multiple users"""
        user_ids = request.data.get('user_ids', [])
        role_id = request.data.get('role_id')
        
        if not role_id:
            return Response(
                {'error': 'role_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            role = Role.objects.get(id=role_id)
            updated_count = 0
            
            for user_id in user_ids:
                try:
                    user = User.objects.get(id=user_id)
                    old_role_id = user.profile.role.id if user.profile.role else None
                    
                    user.profile.role = role
                    user.profile.is_staff = (role.type == 'internal_operator')
                    user.profile.save()
                    
                    # Log each assignment
                    AuditLog.objects.create(
                        actor=request.user,
                        action='role_assign',
                        target_type='user',
                        target_id=str(user.id),
                        target_name=user.username,
                        old_value={'role': old_role_id},
                        new_value={'role': role_id},
                        ip_address=self.get_client_ip(),
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    )
                    
                    updated_count += 1
                except User.DoesNotExist:
                    continue
            
            return Response({
                'message': f'Updated {updated_count} users',
                'updated': updated_count,
            })
        except Role.DoesNotExist:
            return Response(
                {'error': 'Role not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def get_client_ip(self):
        """Get the client IP address from the request"""
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = self.request.META.get('REMOTE_ADDR')
        return ip


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Audit Log viewing (read-only).
    
    Endpoints:
    - GET    /api/admin/rbac/audit-logs/          - List all audit logs
    - GET    /api/admin/rbac/audit-logs/{id}/     - Get audit log details
    - GET    /api/admin/rbac/audit-logs/export/    - Export audit logs (CSV)
    """
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsSuperAdmin]  # Only Super Admin can view full audit log
    required_permission = 'audit.log.view.all'
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by actor if provided
        actor_id = self.request.query_params.get('actor_id')
        if actor_id:
            queryset = queryset.filter(actor_id=actor_id)
        
        # Filter by action if provided
        action = self.request.query_params.get('action')
        if action:
            queryset = queryset.filter(action=action)
        
        # Filter by target type if provided
        target_type = self.request.query_params.get('target_type')
        if target_type:
            queryset = queryset.filter(target_type=target_type)
        
        # Filter by date range if provided
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        
        # Search by target name if provided
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(target_name__icontains=search)
        
        return queryset.order_by('-timestamp')
    
    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export audit logs as CSV"""
        import csv
        from django.http import HttpResponse
        
        queryset = self.get_queryset()
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="audit_logs.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Timestamp', 'Actor', 'Action', 'Target Type', 'Target ID', 
            'Target Name', 'Old Value', 'New Value', 'IP Address', 'User Agent'
        ])
        
        for log in queryset:
            writer.writerow([
                log.timestamp,
                log.actor.username,
                log.action,
                log.target_type,
                log.target_id,
                log.target_name,
                str(log.old_value) if log.old_value else '',
                str(log.new_value) if log.new_value else '',
                log.ip_address,
                log.user_agent[:100],  # Truncate user agent
            ])
        
        return response
