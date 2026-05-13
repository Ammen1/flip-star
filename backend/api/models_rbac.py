"""
RBAC (Role-Based Access Control) Models

This module defines the database models for the FlipStar RBAC system:
- Role: Defines user roles (Contestant, Voter, Moderator, etc.)
- Permission: Defines system permissions grouped by domain
- RolePermission: Maps roles to permissions with access levels
- AuditLog: Immutable audit trail for all admin actions
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class Role(models.Model):
    """
    Role model for defining user roles in the system.
    
    Roles are used to group permissions and assign them to users.
    Examples: Contestant, Voter, Moderator, Campaign Manager, Finance, Support, Super Admin
    """
    ROLE_CHOICES = [
        ('contestant', 'Contestant'),
        ('voter', 'Voter'),
        ('moderator', 'Content Moderator'),
        ('campaign_manager', 'Campaign Manager'),
        ('finance', 'Finance/Reconciliation'),
        ('support', 'Customer Support'),
        ('superadmin', 'Super Admin'),
    ]
    
    TYPE_CHOICES = [
        ('platform_user', 'Platform User'),
        ('internal_operator', 'Internal Operator'),
    ]
    
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField(help_text='Description of what this role can do')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, help_text='Type of role: platform user or internal operator')
    surfaces = models.JSONField(default=list, help_text='List of surfaces where this role is applicable')
    is_default = models.BooleanField(default=False, help_text='Is this the default role for new users?')
    is_active = models.BooleanField(default=True, help_text='Is this role currently active?')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='roles_created')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='roles_updated')
    
    class Meta:
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'
        ordering = ['type', 'name']
    
    def __str__(self):
        return f'{self.name} ({self.type})'
    
    def get_user_count(self):
        """Return the number of users with this role"""
        return self.users.count()


class Permission(models.Model):
    """
    Permission model for defining system permissions.
    
    Permissions are grouped by domain (Identity, Content, Campaign, etc.)
    and represent specific actions that can be performed.
    """
    DOMAIN_CHOICES = [
        ('identity', 'Identity'),
        ('content', 'Content'),
        ('campaign', 'Campaign'),
        ('voting', 'Voting'),
        ('payment', 'Payment'),
        ('subscription', 'Subscription'),
        ('wallet', 'Wallet'),
        ('gift', 'Gift'),
        ('support', 'Support'),
        ('gamification', 'Gamification'),
        ('messaging', 'Messaging'),
        ('admin', 'Admin'),
        ('audit', 'Audit'),
    ]
    
    id = models.CharField(max_length=100, primary_key=True)
    domain = models.CharField(max_length=20, choices=DOMAIN_CHOICES, help_text='Domain/category of the permission')
    name = models.CharField(max_length=100, help_text='Human-readable permission name')
    description = models.TextField(help_text='Detailed description of what this permission allows')
    is_active = models.BooleanField(default=True, help_text='Is this permission currently active?')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='permissions_created')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='permissions_updated')
    
    class Meta:
        verbose_name = 'Permission'
        verbose_name_plural = 'Permissions'
        ordering = ['domain', 'name']
    
    def __str__(self):
        return f'{self.domain}.{self.id}'


class RolePermission(models.Model):
    """
    RolePermission model for mapping roles to permissions with access levels.
    
    This is the many-to-many relationship between Role and Permission,
    with an additional access_level field to specify the type of access.
    """
    ACCESS_CHOICES = [
        ('full', 'Full Access'),
        ('read_only', 'Read-Only Access'),
        ('none', 'No Access'),
    ]
    
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='permissions')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name='roles')
    access_level = models.CharField(max_length=10, choices=ACCESS_CHOICES, default='none', help_text='Level of access for this permission')
    conditions = models.JSONField(default=dict, blank=True, help_text='Conditional access rules (e.g., if subscribed)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='role_permissions_created')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='role_permissions_updated')
    
    class Meta:
        verbose_name = 'Role Permission'
        verbose_name_plural = 'Role Permissions'
        unique_together = ['role', 'permission']
        ordering = ['role', 'permission']
    
    def __str__(self):
        return f'{self.role.name} - {self.permission.name} ({self.access_level})'


class AuditLog(models.Model):
    """
    AuditLog model for recording all admin actions.
    
    This model is immutable (no UPDATE or DELETE allowed) to ensure
    the integrity of the audit trail for compliance and security.
    """
    ACTION_CHOICES = [
        ('role_assign', 'Role Assignment'),
        ('role_revoke', 'Role Revocation'),
        ('permission_grant', 'Permission Granted'),
        ('permission_revoke', 'Permission Revoked'),
        ('user_suspend', 'User Suspended'),
        ('user_unsuspend', 'User Unsuspended'),
        ('config_change', 'Platform Configuration Changed'),
        ('role_create', 'Role Created'),
        ('role_update', 'Role Updated'),
        ('role_delete', 'Role Deleted'),
        ('permission_create', 'Permission Created'),
        ('permission_update', 'Permission Updated'),
        ('permission_delete', 'Permission Deleted'),
        ('role_permission_update', 'Role Permission Updated'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='audit_actions', help_text='User who performed the action')
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, help_text='Type of action performed')
    target_type = models.CharField(max_length=50, help_text='Type of target (user, role, permission, etc.)')
    target_id = models.CharField(max_length=100, help_text='ID of the target object')
    target_name = models.CharField(max_length=200, blank=True, help_text='Human-readable name of the target')
    old_value = models.JSONField(null=True, blank=True, help_text='Previous value before change')
    new_value = models.JSONField(null=True, blank=True, help_text='New value after change')
    ip_address = models.GenericIPAddressField(help_text='IP address of the actor')
    user_agent = models.TextField(help_text='User agent string of the actor')
    timestamp = models.DateTimeField(auto_now_add=True, help_text='When the action occurred')
    
    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['actor']),
            models.Index(fields=['action']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['target_type', 'target_id']),
        ]
    
    def __str__(self):
        return f'{self.action} on {self.target_type}:{self.target_id} by {self.actor.username} at {self.timestamp}'
    
    def save(self, *args, **kwargs):
        """Override save to prevent updates (immutable)"""
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():  # If this is an update (not a new record)
            raise ValueError("AuditLog entries are immutable and cannot be updated")
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Override delete to prevent deletion (immutable)"""
        raise ValueError("AuditLog entries are immutable and cannot be deleted")
