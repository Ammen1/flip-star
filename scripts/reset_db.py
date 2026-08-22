import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

# Delete all users
User.objects.all().delete()
print("✅ All users deleted")

# Create a test user
user = User.objects.create_user(
    username='demo',
    email='demo@example.com',
    password='demo12345',
    first_name='Demo',
    last_name='User'
)
print(f"✅ Test user created: {user.username}")

# Create or get token
token, created = Token.objects.get_or_create(user=user)
print(f"✅ Token created: {token.key}")

print("\n📝 Test Credentials:")
print(f"Email: demo@example.com")
print(f"Password: demo12345")
print(f"Token: {token.key}")
