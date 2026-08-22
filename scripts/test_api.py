import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from api.models import UserProfile, Subscription, NotificationPreference

# Delete if exists
User.objects.filter(username='testuser').delete()

# Create a test user
user = User.objects.create_user(
    username='testuser',
    email='test@example.com',
    password='testpass123',
    first_name='Test',
    last_name='User'
)

print(f"✓ User created: {user.username}")
print(f"✓ User ID: {user.id}")
print(f"✓ Email: {user.email}")

# Check if profile was auto-created
profile = user.profile
print(f"✓ Profile created: Level {profile.level}, XP {profile.xp}")

# Check subscription
sub = user.subscription
print(f"✓ Subscription: {sub.plan}")

# Check notification prefs
notif = user.notification_prefs
print(f"✓ Notification prefs created")

print("\n✅ All tables created successfully!")
