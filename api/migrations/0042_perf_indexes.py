"""Performance indexes — small, safe, additive.

Adds a composite index on (reel, -created_at) to Comment so the per-reel
"recent comments" prefetch used by the feed serializer scans the index
instead of the whole table.  All other hot columns already have indexes.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0041_add_missing_comment_fields_safe'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='comment',
            index=models.Index(fields=['reel', '-created_at'], name='api_comment_reel_cr_idx'),
        ),
    ]
