"""
Seed the coin packages offered for Telebirr purchase.

The lineup lives in api/services/coin_packages.py, which api/views/wallet.py
also reads for its empty-table fallback. Keeping it there rather than here
means the prices a user is shown before seeding and the rows created by
seeding cannot drift apart.

Idempotent: keyed on price_etb, so re-running updates the existing row rather
than creating a second one at the same price. Any active package whose price
is no longer offered is deactivated rather than deleted -- CoinTransaction
rows reference these, and removing one would orphan the audit trail for
purchases already made against it.
"""

from django.core.management.base import BaseCommand

from api.models.contest import CoinPackage
from api.services.coin_packages import COIN_PACKAGES, SUPPORTED_PRICES


class Command(BaseCommand):
    help = 'Seed/update coin packages for Telebirr purchase (idempotent)'

    def handle(self, *args, **options):
        stale = CoinPackage.objects.filter(is_active=True).exclude(price_etb__in=SUPPORTED_PRICES)
        stale_names = list(stale.values_list('name', 'price_etb'))
        deactivated = stale.update(is_active=False)

        if deactivated:
            for name, price in stale_names:
                self.stdout.write(
                    self.style.WARNING(f'Deactivated: {name} - {price} ETB (no longer offered)')
                )

        for pkg_data in COIN_PACKAGES:
            pkg, created = CoinPackage.objects.update_or_create(
                price_etb=pkg_data['price_etb'],
                defaults={**pkg_data, 'is_active': True},
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(
                self.style.SUCCESS(
                    f'{action}: {pkg.name} - {pkg.price_etb} ETB = {pkg.get_total_coins()} coins',
                )
            )

        active = CoinPackage.objects.filter(is_active=True).count()
        self.stdout.write(self.style.SUCCESS(f'Coin packages seeded. Active: {active}'))
