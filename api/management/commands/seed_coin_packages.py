from django.core.management.base import BaseCommand

from api.models.contest import CoinPackage


class Command(BaseCommand):
    help = 'Seed/update coin packages for Telebirr purchase'

    def handle(self, *args, **options):
        # Matches the fallback lineup api/views/wallet.py:get_wallet_config
        # already serves when the CoinPackage table is empty -- seeding the
        # real rows with the same numbers keeps both paths consistent,
        # rather than porting master's own (different) price/coin tiers.
        packages_data = [
            {'name': 'Starter Pack', 'price_etb': 10, 'coin_amount': 100, 'bonus_coins': 0, 'is_featured': False, 'sort_order': 1},
            {'name': 'Good Value', 'price_etb': 25, 'coin_amount': 250, 'bonus_coins': 25, 'is_featured': False, 'sort_order': 2},
            {'name': 'Most Popular', 'price_etb': 50, 'coin_amount': 500, 'bonus_coins': 75, 'is_featured': True, 'sort_order': 3},
            {'name': 'Best Deal', 'price_etb': 100, 'coin_amount': 1000, 'bonus_coins': 200, 'is_featured': False, 'sort_order': 4},
            {'name': 'Premium Package', 'price_etb': 250, 'coin_amount': 2500, 'bonus_coins': 625, 'is_featured': False, 'sort_order': 5},
        ]

        target_prices = {p['price_etb'] for p in packages_data}
        stale_count = CoinPackage.objects.exclude(price_etb__in=target_prices).update(is_active=False)
        if stale_count:
            self.stdout.write(self.style.WARNING(f'Deactivated {stale_count} stale package(s) not in the current lineup'))

        for pkg_data in packages_data:
            pkg, created = CoinPackage.objects.update_or_create(
                price_etb=pkg_data['price_etb'],
                defaults={**pkg_data, 'is_active': True},
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(
                f'{action}: {pkg.name} - {pkg.price_etb} ETB = {pkg.get_total_coins()} coins',
            ))

        self.stdout.write(self.style.SUCCESS('Coin packages seeded successfully.'))
