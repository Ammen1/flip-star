"""
Django management command to seed initial RBAC data (roles, permissions, role-permission mappings)
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models_rbac import Role, Permission, RolePermission


class Command(BaseCommand):
    help = 'Seed initial RBAC data (roles, permissions, role-permission mappings)'

    def handle(self, *args, **options):
        self.stdout.write('Seeding RBAC data...')
        
        # Get or create a superuser for the created_by/updated_by fields
        superuser = User.objects.filter(is_superuser=True).first()
        if not superuser:
            self.stdout.write(self.style.WARNING('No superuser found. Creating a temporary superuser for seeding...'))
            superuser = User.objects.create_superuser(
                username='temp_superuser',
                email='temp@flipstar.com',
                password='TempPassword123!',
                is_staff=True,
                is_superuser=True
            )
            self.stdout.write(self.style.SUCCESS('Created temporary superuser: temp_superuser'))
        
        # Seed Roles
        self.stdout.write('Seeding roles...')
        roles_data = [
            {
                'id': 'contestant',
                'name': 'Contestant',
                'description': 'Authenticated user who uploads Flips and competes in campaigns',
                'type': 'platform_user',
                'surfaces': ['mobile', 'web'],
                'is_default': True,
                'is_active': True,
            },
            {
                'id': 'voter',
                'name': 'Voter',
                'description': 'Authenticated user who browses and votes on content (does not upload)',
                'type': 'platform_user',
                'surfaces': ['mobile', 'web'],
                'is_default': False,
                'is_active': True,
            },
            {
                'id': 'moderator',
                'name': 'Content Moderator',
                'description': 'Reviews and removes inappropriate content',
                'type': 'internal_operator',
                'surfaces': ['web'],
                'is_default': False,
                'is_active': True,
            },
            {
                'id': 'campaign_manager',
                'name': 'Campaign Manager',
                'description': 'Creates and manages campaigns, scoring, and prizes',
                'type': 'internal_operator',
                'surfaces': ['web'],
                'is_default': False,
                'is_active': True,
            },
            {
                'id': 'finance',
                'name': 'Finance/Reconciliation',
                'description': 'Views payment transactions and billing records',
                'type': 'internal_operator',
                'surfaces': ['web'],
                'is_default': False,
                'is_active': True,
            },
            {
                'id': 'support',
                'name': 'Customer Support',
                'description': 'Helps users with account issues, subscriptions, and general support',
                'type': 'internal_operator',
                'surfaces': ['web'],
                'is_default': False,
                'is_active': True,
            },
            {
                'id': 'superadmin',
                'name': 'Super Admin',
                'description': 'Full platform access (CTO/technical lead only)',
                'type': 'internal_operator',
                'surfaces': ['web'],
                'is_default': False,
                'is_active': True,
            },
        ]
        
        roles = {}
        for role_data in roles_data:
            role, created = Role.objects.update_or_create(
                id=role_data['id'],
                defaults={
                    **role_data,
                    'created_by': superuser,
                    'updated_by': superuser,
                }
            )
            roles[role.id] = role
            if created:
                self.stdout.write(self.style.SUCCESS(f'  Created role: {role.name}'))
            else:
                self.stdout.write(f'  Updated role: {role.name}')
        
        # Seed Permissions
        self.stdout.write('Seeding permissions...')
        permissions_data = [
            # Identity Domain
            {'id': 'identity.register', 'domain': 'identity', 'name': 'Register', 'description': 'Create a new account via OTP'},
            {'id': 'identity.login', 'domain': 'identity', 'name': 'Login', 'description': 'Log in and get session token'},
            {'id': 'identity.logout', 'domain': 'identity', 'name': 'Logout', 'description': 'Log out and invalidate session'},
            {'id': 'identity.profile.edit.own', 'domain': 'identity', 'name': 'Edit Own Profile', 'description': 'Edit own profile (name, bio, avatar)'},
            {'id': 'identity.profile.view.any', 'domain': 'identity', 'name': 'View Any Profile', 'description': 'View any user\'s profile (read-only)'},
            {'id': 'identity.user.suspend', 'domain': 'identity', 'name': 'Suspend User', 'description': 'Suspend a user account temporarily'},
            {'id': 'identity.user.manage', 'domain': 'identity', 'name': 'Manage Users', 'description': 'Full user CRUD, role assignment, password reset'},
            {'id': 'identity.operator.manage', 'domain': 'identity', 'name': 'Manage Operators', 'description': 'Create/revoke internal operator accounts'},
            
            # Content Domain
            {'id': 'content.flip.upload', 'domain': 'content', 'name': 'Upload Flip', 'description': 'Upload video or photo to S3'},
            {'id': 'content.flip.view', 'domain': 'content', 'name': 'View Flips', 'description': 'Browse the Flip feed'},
            {'id': 'content.flip.delete.own', 'domain': 'content', 'name': 'Delete Own Flip', 'description': 'Delete own uploaded content'},
            {'id': 'content.flip.flag', 'domain': 'content', 'name': 'Flag Content', 'description': 'Flag/remove any Flip (moderation)'},
            {'id': 'content.flip.view.flagged', 'domain': 'content', 'name': 'View Flagged Content', 'description': 'View flagged content queue'},
            
            # Campaign Domain
            {'id': 'campaign.view', 'domain': 'campaign', 'name': 'View Campaigns', 'description': 'Browse all campaigns'},
            {'id': 'campaign.enter', 'domain': 'campaign', 'name': 'Enter Campaign', 'description': 'Submit a Flip entry to a campaign'},
            {'id': 'campaign.create', 'domain': 'campaign', 'name': 'Create Campaign', 'description': 'Create a new campaign'},
            {'id': 'campaign.edit', 'domain': 'campaign', 'name': 'Edit Campaign', 'description': 'Update campaign metadata, weights, prizes'},
            {'id': 'campaign.close', 'domain': 'campaign', 'name': 'Close Campaign', 'description': 'End an active campaign'},
            {'id': 'campaign.score.trigger', 'domain': 'campaign', 'name': 'Trigger Scoring', 'description': 'Trigger scoring engine recalculation'},
            {'id': 'campaign.reward.distribute', 'domain': 'campaign', 'name': 'Distribute Rewards', 'description': 'Mark winners and distribute prizes'},
            {'id': 'campaign.snapshot.view', 'domain': 'campaign', 'name': 'View Scoring Snapshot', 'description': 'View scoring audit trail'},
            
            # Voting Domain
            {'id': 'voting.cast', 'domain': 'voting', 'name': 'Cast Vote', 'description': 'Pay via Telebirr to vote on a Flip'},
            {'id': 'voting.view.own', 'domain': 'voting', 'name': 'View Own Votes', 'description': 'See own voting history'},
            {'id': 'voting.view.all', 'domain': 'voting', 'name': 'View All Votes', 'description': 'View platform-wide vote data (admin)'},
            {'id': 'voting.invalidate', 'domain': 'voting', 'name': 'Invalidate Vote', 'description': 'Mark a vote as fraudulent'},
            
            # Payment Domain
            {'id': 'payment.initiate', 'domain': 'payment', 'name': 'Initiate Payment', 'description': 'Start a Telebirr payment for a vote'},
            {'id': 'payment.view.own', 'domain': 'payment', 'name': 'View Own Payments', 'description': 'Read own payment history'},
            {'id': 'payment.view.all', 'domain': 'payment', 'name': 'View All Payments', 'description': 'Full payment ledger (read-only)'},
            {'id': 'payment.export', 'domain': 'payment', 'name': 'Export Payments', 'description': 'Download CSV of transaction data'},
            
            # Subscription Domain
            {'id': 'sub.subscribe', 'domain': 'subscription', 'name': 'Subscribe', 'description': 'Subscribe to Premium via Ethio Telecom'},
            {'id': 'sub.unsubscribe', 'domain': 'subscription', 'name': 'Unsubscribe', 'description': 'Cancel own subscription'},
            {'id': 'sub.access.premium', 'domain': 'subscription', 'name': 'Access Premium', 'description': 'Access premium-tier campaigns'},
            {'id': 'sub.view.status.own', 'domain': 'subscription', 'name': 'View Own Subscription', 'description': 'See own plan, renewal date, billing status'},
            {'id': 'sub.view.status.any', 'domain': 'subscription', 'name': 'View Any Subscription', 'description': 'See any user\'s subscription state'},
            {'id': 'sub.cancel.behalf', 'domain': 'subscription', 'name': 'Cancel on Behalf', 'description': 'Cancel subscription on user\'s behalf (support)'},
            {'id': 'sub.view.billing.all', 'domain': 'subscription', 'name': 'View Billing Ledger', 'description': 'Full subscription billing ledger'},
            
            # Wallet Domain
            {'id': 'wallet.view.own', 'domain': 'wallet', 'name': 'View Own Wallet', 'description': 'View own wallet balance'},
            {'id': 'wallet.view.all', 'domain': 'wallet', 'name': 'View All Wallets', 'description': 'View all user wallets (admin)'},
            {'id': 'wallet.withdraw', 'domain': 'wallet', 'name': 'Request Withdrawal', 'description': 'Request withdrawal'},
            {'id': 'wallet.withdraw.approve', 'domain': 'wallet', 'name': 'Approve Withdrawal', 'description': 'Approve withdrawal requests'},
            {'id': 'wallet.withdraw.cancel', 'domain': 'wallet', 'name': 'Cancel Withdrawal', 'description': 'Cancel withdrawal'},
            {'id': 'wallet.config.manage', 'domain': 'wallet', 'name': 'Manage Wallet Config', 'description': 'Manage wallet configuration (min points, rates)'},
            
            # Gift Domain
            {'id': 'gift.send', 'domain': 'gift', 'name': 'Send Gift', 'description': 'Send gifts to other users'},
            {'id': 'gift.receive', 'domain': 'gift', 'name': 'Receive Gift', 'description': 'Receive gifts'},
            {'id': 'gift.view.all', 'domain': 'gift', 'name': 'View All Gifts', 'description': 'View all gift transactions (admin)'},
            {'id': 'gift.config.manage', 'domain': 'gift', 'name': 'Manage Gift Config', 'description': 'Manage gift configuration (prices, conversion)'},
            
            # Support Domain
            {'id': 'support.ticket.create', 'domain': 'support', 'name': 'Create Ticket', 'description': 'Create support ticket'},
            {'id': 'support.ticket.view.own', 'domain': 'support', 'name': 'View Own Tickets', 'description': 'View own tickets'},
            {'id': 'support.ticket.view.all', 'domain': 'support', 'name': 'View All Tickets', 'description': 'View all tickets (admin)'},
            {'id': 'support.ticket.respond', 'domain': 'support', 'name': 'Respond to Ticket', 'description': 'Respond to tickets'},
            {'id': 'support.ticket.close', 'domain': 'support', 'name': 'Close Ticket', 'description': 'Close tickets'},
            
            # Gamification Domain
            {'id': 'gamification.daily.claim', 'domain': 'gamification', 'name': 'Claim Daily Bonus', 'description': 'Claim daily login bonus'},
            {'id': 'gamification.spin', 'domain': 'gamification', 'name': 'Spin Wheel', 'description': 'Use daily spin wheel'},
            {'id': 'gamification.config.manage', 'domain': 'gamification', 'name': 'Manage Gamification Config', 'description': 'Manage gamification config (bonuses, streaks)'},
            
            # Messaging Domain
            {'id': 'message.send', 'domain': 'messaging', 'name': 'Send Message', 'description': 'Send messages to other users'},
            {'id': 'message.view.own', 'domain': 'messaging', 'name': 'View Own Messages', 'description': 'View own messages'},
            {'id': 'message.view.all', 'domain': 'messaging', 'name': 'View All Messages', 'description': 'View all messages (admin)'},
            
            # Admin Domain
            {'id': 'admin.dashboard', 'domain': 'admin', 'name': 'Admin Dashboard', 'description': 'Access Django Admin dashboard'},
            {'id': 'admin.settings', 'domain': 'admin', 'name': 'Admin Settings', 'description': 'Configure platform settings'},
            {'id': 'admin.role.assign', 'domain': 'admin', 'name': 'Assign Roles', 'description': 'Assign/revoke roles to users'},
            
            # Audit Domain
            {'id': 'audit.log.view.own', 'domain': 'audit', 'name': 'View Own Audit Log', 'description': 'View own admin actions'},
            {'id': 'audit.log.view.all', 'domain': 'audit', 'name': 'View All Audit Logs', 'description': 'View full audit log (Super Admin)'},
            {'id': 'audit.log.export', 'domain': 'audit', 'name': 'Export Audit Log', 'description': 'Export audit log for compliance (INSA)'},
        ]
        
        permissions = {}
        for perm_data in permissions_data:
            permission, created = Permission.objects.update_or_create(
                id=perm_data['id'],
                defaults={
                    **perm_data,
                    'created_by': superuser,
                    'updated_by': superuser,
                }
            )
            permissions[permission.id] = permission
            if created:
                self.stdout.write(self.style.SUCCESS(f'  Created permission: {permission.domain}.{permission.name}'))
            else:
                self.stdout.write(f'  Updated permission: {permission.domain}.{permission.name}')
        
        # Seed Role-Permission Mappings based on the matrix
        self.stdout.write('Seeding role-permission mappings...')
        
        # Define the access matrix: {role_id: {permission_id: access_level}}
        access_matrix = {
            'contestant': {
                'identity.register': 'full',
                'identity.login': 'full',
                'identity.logout': 'full',
                'identity.profile.edit.own': 'full',
                'content.flip.upload': 'full',
                'content.flip.view': 'full',
                'content.flip.delete.own': 'full',
                'campaign.view': 'full',
                'campaign.enter': 'full',
                'voting.cast': 'full',
                'voting.view.own': 'full',
                'payment.initiate': 'full',
                'payment.view.own': 'full',
                'sub.subscribe': 'full',
                'sub.unsubscribe': 'full',
                'sub.access.premium': 'read_only',
                'sub.view.status.own': 'full',
                'wallet.view.own': 'full',
                'wallet.withdraw': 'full',
                'gift.send': 'full',
                'gift.receive': 'full',
                'support.ticket.create': 'full',
                'support.ticket.view.own': 'full',
                'gamification.daily.claim': 'full',
                'gamification.spin': 'full',
                'message.send': 'full',
                'message.view.own': 'full',
            },
            'voter': {
                'identity.register': 'full',
                'identity.login': 'full',
                'identity.logout': 'full',
                'identity.profile.edit.own': 'full',
                'content.flip.view': 'full',
                'campaign.view': 'full',
                'voting.cast': 'full',
                'voting.view.own': 'full',
                'payment.initiate': 'full',
                'payment.view.own': 'full',
                'sub.subscribe': 'full',
                'sub.unsubscribe': 'full',
                'sub.access.premium': 'read_only',
                'sub.view.status.own': 'full',
                'wallet.view.own': 'full',
                'gift.receive': 'full',
                'support.ticket.create': 'full',
                'support.ticket.view.own': 'full',
                'gamification.daily.claim': 'full',
                'gamification.spin': 'full',
            },
            'moderator': {
                'identity.login': 'full',
                'identity.logout': 'full',
                'identity.profile.view.any': 'read_only',
                'identity.user.suspend': 'read_only',
                'content.flip.view': 'full',
                'content.flip.flag': 'full',
                'content.flip.view.flagged': 'full',
                'campaign.view': 'full',
                'campaign.snapshot.view': 'read_only',
                'admin.dashboard': 'full',
                'audit.log.view.own': 'full',
            },
            'campaign_manager': {
                'identity.login': 'full',
                'identity.logout': 'full',
                'identity.profile.view.any': 'read_only',
                'content.flip.view': 'full',
                'campaign.view': 'full',
                'campaign.create': 'full',
                'campaign.edit': 'full',
                'campaign.close': 'full',
                'campaign.score.trigger': 'full',
                'campaign.reward.distribute': 'full',
                'campaign.snapshot.view': 'read_only',
                'voting.view.all': 'read_only',
                'voting.invalidate': 'full',
                'admin.dashboard': 'full',
                'audit.log.view.own': 'full',
            },
            'finance': {
                'identity.login': 'full',
                'identity.logout': 'full',
                'campaign.view': 'read_only',
                'campaign.snapshot.view': 'read_only',
                'voting.view.all': 'full',
                'payment.view.all': 'full',
                'payment.export': 'full',
                'sub.view.status.any': 'full',
                'sub.view.billing.all': 'full',
                'wallet.view.all': 'full',
                'wallet.withdraw.approve': 'full',
                'gift.view.all': 'full',
                'admin.dashboard': 'full',
                'audit.log.view.own': 'full',
                'audit.log.export': 'full',
            },
            'support': {
                'identity.login': 'full',
                'identity.logout': 'full',
                'identity.profile.view.any': 'read_only',
                'campaign.view': 'read_only',
                'payment.view.own': 'read_only',
                'sub.view.status.any': 'full',
                'sub.cancel.behalf': 'full',
                'wallet.view.all': 'full',
                'wallet.withdraw.cancel': 'full',
                'gift.view.all': 'read_only',
                'support.ticket.view.all': 'full',
                'support.ticket.respond': 'full',
                'support.ticket.close': 'full',
                'admin.dashboard': 'full',
                'audit.log.view.own': 'full',
            },
            'superadmin': {
                # Super Admin gets full access to all permissions
                **{perm_id: 'full' for perm_id in permissions.keys()}
            },
        }
        
        mappings_created = 0
        mappings_updated = 0
        
        for role_id, perm_access in access_matrix.items():
            role = roles.get(role_id)
            if not role:
                self.stdout.write(self.style.WARNING(f'  Role {role_id} not found, skipping'))
                continue
            
            for perm_id, access_level in perm_access.items():
                permission = permissions.get(perm_id)
                if not permission:
                    self.stdout.write(self.style.WARNING(f'  Permission {perm_id} not found, skipping'))
                    continue
                
                role_perm, created = RolePermission.objects.update_or_create(
                    role=role,
                    permission=permission,
                    defaults={
                        'access_level': access_level,
                        'created_by': superuser,
                        'updated_by': superuser,
                    }
                )
                
                if created:
                    mappings_created += 1
                    self.stdout.write(f'  Created mapping: {role.name} - {permission.name} ({access_level})')
                else:
                    mappings_updated += 1
                    self.stdout.write(f'  Updated mapping: {role.name} - {permission.name} ({access_level})')
        
        self.stdout.write(self.style.SUCCESS(f'\nRBAC data seeded successfully!'))
        self.stdout.write(f'  Roles: {len(roles)}')
        self.stdout.write(f'  Permissions: {len(permissions)}')
        self.stdout.write(f'  Role-Permission Mappings Created: {mappings_created}')
        self.stdout.write(f'  Role-Permission Mappings Updated: {mappings_updated}')
