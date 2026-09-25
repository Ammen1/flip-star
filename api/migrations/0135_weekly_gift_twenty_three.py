"""Weekly per-charge gift: 25 coins -> 23.

The plan pays 4 coins on days one and two and 3 on each of days three to
seven, which is 23. It was seeded at 25 by migration 0128, and
subscription_daily_gift.daily_schedule spreads whatever total it is given
across the period with the remainder on the earliest days -- so 25 rendered as
4/4/4/4/3/3/3 and paid two coins more than the plan promises.

The schedule itself is correct and unchanged: 23 across 7 days is exactly
4/4/3/3/3/3/3.

Only a tier still holding 0128's 25 is touched, so an amount somebody has
deliberately set in the admin survives. Reversible, because the previous value
is equally well defined.
"""

from django.db import migrations

WEEKLY_WAS = 25
WEEKLY_NOW = 23


def set_weekly(apps, schema_editor):
    SubscriptionTier = apps.get_model('api', 'SubscriptionTier')
    SubscriptionTier.objects.filter(duration_type='weekly', charge_gift_coins=WEEKLY_WAS).update(
        charge_gift_coins=WEEKLY_NOW
    )


def unset_weekly(apps, schema_editor):
    SubscriptionTier = apps.get_model('api', 'SubscriptionTier')
    SubscriptionTier.objects.filter(duration_type='weekly', charge_gift_coins=WEEKLY_NOW).update(
        charge_gift_coins=WEEKLY_WAS
    )


class Migration(migrations.Migration):
    dependencies = [('api', '0134_subscription_only_verification_purpose')]

    operations = [migrations.RunPython(set_weekly, unset_weekly)]
