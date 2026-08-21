# Generated manually to add category system.
#
# NEUTRALISED. This migration was an exact duplicate of 0078, which already
# creates the Category model and adds Reel.category. Because 0079 depends on
# 0078, running both in order aborted any fresh build with:
#
#     django.db.utils.OperationalError: table "api_category" already exists
#
# The operations list is now empty rather than the file being deleted, so
# databases that already record 0079 as applied stay consistent. The migration
# state after 0079 is identical either way, since it added nothing 0078 had not
# already added.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0078_category_alter_walletconfig_cost_comment_and_more'),
    ]

    operations = []
