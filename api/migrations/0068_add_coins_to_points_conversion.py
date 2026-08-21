# Generated migration to add missing coins_to_points_conversion column
#
# NEUTRALIZED: WalletConfig.coins_to_points_conversion was already added by
# migration 0051 (part of a larger AddField batch). This migration was
# generated later against a local database that had apparently been patched
# out-of-band, so Django believed the field was still missing. Replaying it
# against a genuinely fresh database duplicates the AddField and fails with
# "column ... already exists" (found while building a fresh PostgreSQL
# database for race-condition concurrency tests -- the same class of bug as
# 0079_add_category_system, fixed the same way: operations emptied, the
# migration node kept so migration 0069's dependency on it still resolves).
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0066_add_gifts_weight_to_scoring_config'),
    ]

    operations = []
