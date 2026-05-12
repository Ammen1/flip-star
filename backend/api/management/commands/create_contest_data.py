"""
Create initial contest data management command
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from api.models_contest import ContestTimeline, CoinPackage

class Command(BaseCommand):
    help = 'Create initial contest timeline and coin packages'

    def handle(self, *args, **options):
        # Create main contest timeline
        contest, created = ContestTimeline.objects.get_or_create(
            name="Summer Contest 2024",
            defaults={
                'start_date': timezone.now(),
                'end_date': timezone.now() + timedelta(days=90),
                'total_budget': 2100000,  # 2.1 Million ETB
                'flash_start_time': timezone.now().time().replace(hour=18, minute=0),
                'flash_end_time': timezone.now().time().replace(hour=20, minute=0),
                'is_active': True,
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created contest: {contest.name}'))
        else:
            self.stdout.write(self.style.WARNING(f'Contest already exists: {contest.name}'))
        
        # Create coin packages
        packages = [
            {'name': 'Starter', 'price_etb': 10, 'coins': 100, 'bonus_coins': 0},
            {'name': 'Bronze', 'price_etb': 25, 'coins': 250, 'bonus_coins': 25},
            {'name': 'Silver', 'price_etb': 50, 'coins': 500, 'bonus_coins': 75},
            {'name': 'Gold', 'price_etb': 100, 'coins': 1000, 'bonus_coins': 200},
            {'name': 'Platinum', 'price_etb': 250, 'coins': 2500, 'bonus_coins': 625},
            {'name': 'Diamond', 'price_etb': 500, 'coins': 5000, 'bonus_coins': 1500},
        ]
        
        created_count = 0
        for pkg_data in packages:
            pkg, created = CoinPackage.objects.get_or_create(
                name=pkg_data['name'],
                defaults=pkg_data
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created package: {pkg.name}'))
        
        self.stdout.write(self.style.SUCCESS(f'Created {created_count} new coin packages'))
        self.stdout.write(self.style.SUCCESS('Initial contest data created successfully!'))
