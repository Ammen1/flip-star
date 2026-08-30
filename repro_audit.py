"""Reproduce /subscription/status/ against the real view, in-process."""

import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# E402 is unavoidable here: Django models cannot be imported before
# django.setup() has run, and setup() needs the two lines above it.
from django.contrib.auth import get_user_model  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

User = get_user_model()
URL = '/api/v1/subscription/status/'


def show(label, r):
    body = getattr(r, 'data', None)
    if body is None:
        body = r.content[:200]
    print(f'{label:<32} -> {r.status_code}  {str(body)[:200]}')


c = APIClient()
show('unauthenticated', c.get(URL))

u, created = User.objects.get_or_create(
    username='audit_nosub', defaults={'email': 'nosub@test.local'}
)
c.force_authenticate(user=u)
show('authed, zero subscriptions', c.get(URL))

print('\n-- every existing user --')
total = User.objects.count()
bad = 0
c2 = APIClient()
for user in User.objects.all()[:40]:
    c2.force_authenticate(user=user)
    r = c2.get(URL)
    if r.status_code != 200:
        bad += 1
        print(
            f'  !! id={user.id} user={user.username!r} -> {r.status_code} '
            f'{str(getattr(r, "data", r.content))[:220]}'
        )
print(f'users in db: {total} | checked: {min(40, total)} | non-200: {bad}')
