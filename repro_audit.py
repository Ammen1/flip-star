"""Reproduce /subscription/status/ against the real view, in-process."""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()
URL = '/api/v1/subscription/status/'

def show(label, r):
    body = getattr(r, 'data', None)
    if body is None:
        body = r.content[:200]
    print('%-32s -> %s  %s' % (label, r.status_code, str(body)[:200]))

c = APIClient()
show('unauthenticated', c.get(URL))

u, created = User.objects.get_or_create(username='audit_nosub', defaults={'email': 'nosub@test.local'})
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
        print('  !! id=%s user=%r -> %s %s' % (user.id, user.username, r.status_code,
              str(getattr(r, 'data', r.content))[:220]))
print('users in db: %d | checked: %d | non-200: %d' % (total, min(40, total), bad))
