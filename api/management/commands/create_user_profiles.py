from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models import UserProfile

class Command(BaseCommand):
    help = 'Create UserProfile for all users that do not have one'

    def handle(self, *args, **options):
        users_without_profile = []
        
        for user in User.objects.all():
            if not hasattr(user, 'profile'):
                UserProfile.objects.create(user=user)
                users_without_profile.append(user.username)
                self.stdout.write(self.style.SUCCESS(f'Created profile for user: {user.username}'))
        
        if not users_without_profile:
            self.stdout.write(self.style.SUCCESS('All users already have profiles'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Created profiles for {len(users_without_profile)} users'))
