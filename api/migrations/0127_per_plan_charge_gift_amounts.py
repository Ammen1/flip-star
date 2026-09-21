"""Per-plan gift coins: weekly 25, monthly 120.

A subscriber earns gift coins ("bones") every time a payment on their plan
completes -- the first subscription and each renewal/charge alike. The amount
lives on the tier (`SubscriptionTier.charge_gift_coins`), and the payout is a
post_save signal on SubscriptionPayment (api/services/subscription_gift.py).
The daily plan already pays like this (3 per charge, the amount the login
bonus used to pay). Give the other two recurring plans their own amounts:
 weekly 25, monthly 120. On-demand buys its coins outright and never uses
this field.
"""

from django.db import migrations

#: slug -> per-charge gift coins. Daily intentionally keeps its current
#: value (the former login bonus, 3) -- nothing to change for it here.
#: On-demand buys its coins outright and is zeroed so the recurring-gift
#: ledger never sees it.
CHARGE_GIFTS = {
    'weekly': 25,
    'monthly': 120,
    'ondemand': 0,
}

#: What the per-charge gift was before this migration for these two tiers:
#: migration 0123 seeded every tier with the former daily login bonus.
PREVIOUS = 3


def set_gifts(apps, schema_editor):
    SubscriptionTier = apps.get_model('api', 'SubscriptionTier')
    for slug, coins in CHARGE_GIFTS.items():
        SubscriptionTier.objects.filter(slug=slug).update(charge_gift_coins=coins)


def clear_gifts(apps, schema_editor):
    SubscriptionTier = apps.get_model('api', 'SubscriptionTier')
    for slug in CHARGE_GIFTS:
        SubscriptionTier.objects.filter(slug=slug).update(charge_gift_coins=PREVIOUS)


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0126_coin_transaction_payment_state'),
    ]

    operations = [
        migrations.RunPython(set_gifts, clear_gifts),
    ]
