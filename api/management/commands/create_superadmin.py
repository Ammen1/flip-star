from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from infrastructure.secrets import secret


class Command(BaseCommand):
    help = 'Create initial super admin user (idempotent - safe to run multiple times)'

    def add_arguments(self, parser):
        # Defaults resolve through environment -> Vault -> .env. `--password`
        # deliberately has no fallback: it used to default to a well-known
        # literal, so a deploy that forgot to set ADMIN_PASSWORD silently
        # created a superuser with a password published in this repository.
        parser.add_argument(
            '--username',
            type=str,
            default=secret('ADMIN_USERNAME', default='superadmin'),
            help='Username for super admin (default: ADMIN_USERNAME, else "superadmin")'
        )
        parser.add_argument(
            '--email',
            type=str,
            default=secret('ADMIN_EMAIL', default='admin@example.com'),
            help='Email for super admin (default: ADMIN_EMAIL)'
        )
        parser.add_argument(
            '--password',
            type=str,
            default=secret('ADMIN_PASSWORD', default=''),
            help='Password for super admin. Required: pass --password or set ADMIN_PASSWORD.'
        )

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']

        if not password:
            raise CommandError(
                'No password supplied. Pass --password, or set ADMIN_PASSWORD in '
                'the environment, Vault, or .env.'
            )

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
