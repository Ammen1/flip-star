from django.core.management.base import BaseCommand
from api.models_gift import Gift


class Command(BaseCommand):
    help = 'Seed default gifts for the gifting system'

    def handle(self, *args, **options):
        default_gifts = [
            {
                'name': 'Rose',
                'description': 'A beautiful red rose for expressing love',
                'coin_value': 10,
                'rarity': 'common',
                'category': 'flowers',
                'sort_order': 1,
                'xp_reward': 5,
                'animation_type': 'bounce',
                'animation_duration': 0.8,
            },
            {
                'name': 'Heart',
                'description': 'A heart symbol to show appreciation',
                'coin_value': 20,
                'rarity': 'common',
                'category': 'hearts',
                'sort_order': 2,
                'xp_reward': 10,
                'animation_type': 'pulse',
                'animation_duration': 0.6,
            },
            {
                'name': 'Medal',
                'description': 'A gold medal for achievements',
                'coin_value': 50,
                'rarity': 'rare',
                'category': 'special',
                'sort_order': 3,
                'xp_reward': 25,
                'animation_type': 'bounce',
                'animation_duration': 1.0,
            },
            {
                'name': 'Diamond',
                'description': 'A sparkling diamond gift',
                'coin_value': 100,
                'rarity': 'epic',
                'category': 'gems',
                'sort_order': 4,
                'xp_reward': 50,
                'animation_type': 'particle',
                'animation_duration': 1.2,
            },
            {
                'name': 'Teddy Bear',
                'description': 'A cute teddy bear for comfort',
                'coin_value': 30,
                'rarity': 'common',
                'category': 'animals',
                'sort_order': 5,
                'xp_reward': 15,
                'animation_type': 'bounce',
                'animation_duration': 0.9,
            },
        ]

        created_count = 0
        updated_count = 0

        for gift_data in default_gifts:
            gift, created = Gift.objects.get_or_create(
                name=gift_data['name'],
                defaults=gift_data
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Created gift: {gift.name} ({gift.coin_value} coins)')
                )
                created_count += 1
            else:
                # Update existing gift with new values
                for key, value in gift_data.items():
                    setattr(gift, key, value)
                gift.save()
                self.stdout.write(
                    self.style.WARNING(f'Updated gift: {gift.name} ({gift.coin_value} coins)')
                )
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully seeded {created_count} new gifts and updated {updated_count} existing gifts'
            )
        )
