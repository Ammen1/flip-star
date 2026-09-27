#!/usr/bin/env python3
"""
Automatic Migration Runner for Render Deployment
This script will run Django migrations on startup
"""

import os
import sys
from pathlib import Path

import django

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def run_migrations():
    """Run Django migrations"""
    try:
        print('🔄 Running Django migrations...')
        django.setup()

        from django.core.management import execute_from_command_line

        execute_from_command_line(['manage.py', 'migrate', '--verbosity=2'])

        print('✅ Migrations completed successfully!')

        # Create superuser if none exists.
        #
        # Audit finding M-06: this used to call create_superuser with the literal
        # password 'admin123' and then print it. Run once against a reachable
        # database and the platform has a known-credential superuser -- and
        # because the literal was committed, the credential is public. The
        # password now comes from the environment and the script refuses rather
        # than inventing one, so there is no path back to a default.
        import os

        from django.contrib.auth.models import User

        if not User.objects.filter(is_superuser=True).exists():
            username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
            email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')
            password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
            if not password:
                print(
                    '⚠️  No superuser exists and DJANGO_SUPERUSER_PASSWORD is not set; '
                    'skipping superuser creation.\n'
                    '    Create one deliberately:\n'
                    '      DJANGO_SUPERUSER_USERNAME=... DJANGO_SUPERUSER_EMAIL=... \\\n'
                    '      DJANGO_SUPERUSER_PASSWORD=... python manage.py createsuperuser --noinput'
                )
            else:
                print('📝 Creating admin user from the environment...')
                User.objects.create_superuser(username=username, email=email, password=password)
                # The password is not echoed. Whoever set it already has it.
                print(f'✅ Admin user created (username: {username})')
        else:
            print('ℹ️ Admin user already exists')

        return True

    except Exception as e:
        print(f'❌ Migration error: {e}')
        return False


if __name__ == '__main__':
    success = run_migrations()
    if not success:
        sys.exit(1)
