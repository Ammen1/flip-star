import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

# Audit finding M-06. This script deletes every user and then creates one with a
# committed literal password. Either half is destructive against a real database;
# together they replace the user table with a known credential. Two guards now
# stand in front of it, because "it is only a dev script" is true right up until
# somebody runs it with the wrong DJANGO_SETTINGS_MODULE.
if not settings.DEBUG:
    raise SystemExit(
        'refusing to run: this script deletes every user, and DEBUG is False.\n'
        'It is a local development helper. If you really mean to reset a '
        'non-DEBUG database, do it deliberately and not through this file.'
    )

_password = os.environ.get('DEMO_USER_PASSWORD', '')
if not _password:
    raise SystemExit(
        'refusing to run: set DEMO_USER_PASSWORD to the password for the demo '
        'account. It used to be a literal in this file, which made it a '
        'published credential.'
    )

# Delete all users
User.objects.all().delete()
print('✅ All users deleted')

# Create a test user
user = User.objects.create_user(
    username='demo',
    email='demo@example.com',
    password=_password,
    first_name='Demo',
    last_name='User',
)
print(f'✅ Test user created: {user.username}')

# Create or get token
token, created = Token.objects.get_or_create(user=user)
print(f'✅ Token created: {token.key}')

print('\n📝 Test Credentials:')
print('Email: demo@example.com')
# Not echoed: whoever set DEMO_USER_PASSWORD has it, and a printed
# credential lands in shell history and CI logs (audit M-06).
print('Password: (the DEMO_USER_PASSWORD you supplied)')
print(f'Token: {token.key}')
