from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
import os

class Command(BaseCommand):
    help = 'Create initial super admin user (idempotent - safe to run multiple times)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            default=os.getenv('ADMIN_USERNAME', 'superadmin'),
            help='Username for super admin (default: superadmin or ADMIN_USERNAME env var)'
        )
        parser.add_argument(
            '--email',
            type=str,
            default=os.getenv('ADMIN_EMAIL', 'superadmin@yourapp.com'),
            help='Email for super admin (default: superadmin@yourapp.com or ADMIN_EMAIL env var)'
        )
        parser.add_argument(
            '--password',
            type=str,
            default=os.getenv('ADMIN_PASSWORD', 'Admin123!'),
            help='Password for super admin (default: Admin123! or ADMIN_PASSWORD env var)'
        )

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']
        
        # Check if user already exists
        existing_user = User.objects.filter(username=username).first()
        if existing_user:
            if existing_user.is_superuser:
                self.stdout.write(
                    self.style.SUCCESS(f'Super admin "{username}" already exists - skipping')
                )
            else:
                # Promote to super admin
                existing_user.is_staff = True
                existing_user.is_superuser = True
                existing_user.save()
                self.stdout.write(
                    self.style.SUCCESS(f'User "{username}" promoted to super admin')
                )
            return
        
        # Check if email already taken by another user
        if User.objects.filter(email=email).exclude(username=username).exists():
            self.stdout.write(
                self.style.WARNING(f'Email "{email}" already used by another user')
            )
            return
            
        # Create super admin
        try:
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
                first_name='Super',
                last_name='Admin'
            )
            self.stdout.write(
                self.style.SUCCESS(f'Super admin "{username}" created successfully!')
            )
            self.stdout.write(f'  - Username: {username}')
            self.stdout.write(f'  - Email: {email}')
            self.stdout.write(f'  - Password: {"*" * len(password)}')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to create super admin: {e}')
            )
