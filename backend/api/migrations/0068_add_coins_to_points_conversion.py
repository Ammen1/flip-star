# Generated migration to add missing coins_to_points_conversion column

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0067_block_onevaschargingtransaction_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='walletconfig',
            name='coins_to_points_conversion',
            field=models.PositiveIntegerField(default=1, help_text='How many coins = 1 point (gift conversion)'),
        ),
    ]
