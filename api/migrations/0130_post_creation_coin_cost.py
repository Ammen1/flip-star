"""Posting costs coins: 2 for a photo or a short video, 100 for a long one.

The machinery already existed -- ``WalletConfig`` carries a base post price and
a long-video difference, the upload request charges the first and the worker
charges the second once it has measured the file. Every one of those fields
was 0, so posting was free and the rule existed only on paper.

This sets them:

    cost_post_create*                 2    every post, charged on upload
    cost_post_create_long_video*      98   added once the video measures 60s+

2 + 98 = 100, which is what a 60-to-120-second video costs in total. The
difference is stored rather than the total because that is how it is charged:
the base is taken before the duration is known, and the rest afterwards.

Campaign and non-campaign are set to the same amounts: the price list the
product gave is by post type and duration, and says nothing about campaigns.
They remain separate fields, so they can diverge later from the admin without
a deploy.

Reversible, and back to what it was: free.
"""

from django.db import migrations

BASE = 2
LONG_VIDEO_EXTRA = 98

FIELDS = {
    'cost_post_create': BASE,
    'cost_post_create_non_campaign': BASE,
    'cost_post_create_long_video': LONG_VIDEO_EXTRA,
    'cost_post_create_long_video_non_campaign': LONG_VIDEO_EXTRA,
}


def set_post_costs(apps, schema_editor):
    WalletConfig = apps.get_model('api', 'WalletConfig')
    # get_config() creates the singleton on first read; in a migration the
    # row may not exist yet, and a config created later picks these up from
    # the field defaults set in the same change.
    WalletConfig.objects.all().update(**FIELDS)


def clear_post_costs(apps, schema_editor):
    WalletConfig = apps.get_model('api', 'WalletConfig')
    WalletConfig.objects.all().update(**dict.fromkeys(FIELDS, 0))


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0129_backfill_payment_state'),
    ]

    operations = [
        migrations.RunPython(set_post_costs, clear_post_costs),
    ]
