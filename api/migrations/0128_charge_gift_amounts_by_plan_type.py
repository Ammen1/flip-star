"""Per-plan gift coins, found by what the plan is rather than by its slug.

Migration 0127 was meant to set the per-charge gift to weekly 25 and monthly
120, but it looked the tiers up by slug. A tier created or renamed in the
admin need not have the slug 'weekly' or 'monthly', and ``filter(slug=...)``
matching nothing is not an error -- so on such a database 0127 applied,
changed nothing, and every plan kept the 3 coins 0123 seeded for all of them.
Subscribers on every plan were gifted 3.

This keys on ``duration_type``, which is what a plan *is* and what the gift
service itself reads, so it cannot miss a tier because of its name.

Only a tier still at 0123's seed value (3) is changed. An amount somebody has
deliberately set in the admin is left alone.
"""

from django.db import migrations

#: duration_type -> per-charge gift coins.
CHARGE_GIFTS = {
    'daily': 3,
    'weekly': 25,
    'monthly': 120,
}

#: What 0123 seeded every tier with. Only tiers still holding it are changed.
SEEDED = 3


def set_gifts(apps, schema_editor):
    SubscriptionTier = apps.get_model('api', 'SubscriptionTier')
    for duration_type, coins in CHARGE_GIFTS.items():
        SubscriptionTier.objects.filter(
            duration_type=duration_type, charge_gift_coins=SEEDED
        ).update(charge_gift_coins=coins)
    # On-demand buys its coins outright (api/services/subscription_gift.py)
    # and never pays the per-charge gift; zero it so the field says so.
    SubscriptionTier.objects.filter(duration_type='ondemand').update(charge_gift_coins=0)


def restore_seed(apps, schema_editor):
    SubscriptionTier = apps.get_model('api', 'SubscriptionTier')
    for duration_type, coins in CHARGE_GIFTS.items():
        SubscriptionTier.objects.filter(
            duration_type=duration_type, charge_gift_coins=coins
        ).update(charge_gift_coins=SEEDED)


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0127_per_plan_charge_gift_amounts'),
    ]

    operations = [
        migrations.RunPython(set_gifts, restore_seed),
    ]
