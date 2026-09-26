"""Give each subscription tier back its TIMWE charging service id.

Why this is needed
------------------
A charge names the MA service the product is provisioned under --
``<v2:serviceId>`` in api/integrations/timwe/charge.py. TIMWE register a
price point per service, so 3 Birr is only valid against the daily service
and 10 Birr only against the on-demand one.

``charging_service_id(tier)`` reads ``SubscriptionTier.service_id`` and falls
back to the deployment-wide ``TIMWE_SERVICE_ID`` when it is blank. On staging
every tier was blank, so all four products charged against the configured
default -- which is ``30026300007334``, the **on-demand** service. The result:

    10 Birr  ->  SVC0001 NO_BALANCE          (valid price point, empty wallet)
     3 Birr  ->  SVC0901 INVALID_PRICEPOINT_ID
    20 Birr  ->  would fail the same way
    70 Birr  ->  would fail the same way

So no subscription renewal could ever have succeeded, whatever
``TIMWE_SUBSCRIPTION_RENEWAL_ENABLED`` was set to.

Migration 0057 seeded these ids correctly. They were lost because
``manage.py seed_subscription_tiers`` creates tiers with
``get_or_create(slug=..., defaults=...)`` and deliberately omits the
provisioning columns -- a tier created by that command starts blank, and no
later run fills it in. That omission is right (re-running must never blank a
stored value); what was missing is anything that puts them back.

Only fills what is empty
------------------------
A tier that already carries a service id is left exactly as it is. This is a
backfill, not a reset: if an environment has been given different ids by
TIMWE, they survive. That also makes it safe to re-run and safe on
production, where the values may already be present.
"""

from django.db import migrations

#: Source: api/migrations/0057_create_subscription_tiers.py, and
#: scripts/populate_subscription_tiers.py, which agree. Keyed by slug --
#: `duration_type` carries the same four values, but slug is what the seed
#: command matches on.
CHARGE_SERVICE_IDS = {
    'daily': '30026300007331',
    'weekly': '30026300007332',
    'monthly': '30026300007333',
    'ondemand': '30026300007334',
}


def backfill(apps, schema_editor):
    SubscriptionTier = apps.get_model('api', 'SubscriptionTier')

    for slug, service_id in CHARGE_SERVICE_IDS.items():
        # `service_id=''` only -- never overwrite one that is already set.
        SubscriptionTier.objects.filter(slug=slug, service_id='').update(service_id=service_id)


def unbackfill(apps, schema_editor):
    """Clear only the ids this migration would have written.

    Reversing restores the state that made charging fail, which is not
    something to do casually -- but a migration that cannot be reversed is
    worse, and a tier carrying some other id is left alone.
    """
    SubscriptionTier = apps.get_model('api', 'SubscriptionTier')

    for slug, service_id in CHARGE_SERVICE_IDS.items():
        SubscriptionTier.objects.filter(slug=slug, service_id=service_id).update(service_id='')


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0142_audit_gaps_notifications_points'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
