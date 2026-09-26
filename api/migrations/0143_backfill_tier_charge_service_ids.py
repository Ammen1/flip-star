"""Fill in a subscription tier's TIMWE charging service id when it is blank.

What this is NOT
----------------
It is not a repair for staging. Staging's four tiers already carry the right
ids -- verified against the live database, which returns 30026300007331 /
7332 / 7333 / 7334 for daily / weekly / monthly / ondemand. This migration
finds nothing to do there, and that is the expected outcome.

What it guards
--------------
``manage.py seed_subscription_tiers`` creates tiers with
``get_or_create(slug=..., defaults=...)`` and deliberately omits the
provisioning columns (spid / service_id / product_id / application_key) so
that re-running it can never blank a stored ``product_id``. That omission is
right. Its consequence is that a tier *created* by that command starts with
``service_id=''`` and nothing ever fills it in -- so a freshly seeded
environment charges every product against the deployment-wide
``TIMWE_SERVICE_ID`` instead of its own service.

Why that matters
----------------
A charge names the MA service the product is provisioned under
(``<v2:serviceId>`` in api/integrations/timwe/charge.py) and TIMWE register a
price point per service. 3 Birr is valid against the daily service and not
against the on-demand one, which is what ``TIMWE_SERVICE_ID`` happens to hold
-- so a blank tier would charge 3 Birr at the 10 Birr service and get
``SVC0901 INVALID_PRICEPOINT_ID`` on every renewal, hourly, for a week.

``charging_service_id(tier)`` returns '' for a blank tier and the caller falls
back to the default, so nothing fails loudly; it just quietly charges the
wrong service.

Only fills what is empty
------------------------
A tier that already carries an id keeps it, whatever it is. This is a
backfill, not a reset: an environment TIMWE issued different ids to survives
untouched, and re-running is a no-op. That is what makes it safe to apply
everywhere, including production, where the values are expected to be present
already.
"""

from django.db import migrations

#: Source: api/migrations/0057_create_subscription_tiers.py and
#: scripts/populate_subscription_tiers.py, which agree with each other and
#: with the live staging database. Keyed by slug, which is what the seed
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

    A tier carrying some other id is left alone, so reversing cannot destroy
    a value this migration did not put there.
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
