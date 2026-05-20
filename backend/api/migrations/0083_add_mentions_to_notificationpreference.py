# Generated manually to fix missing mentions field in NotificationPreference model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0082_walletconfig_cost_boost_1hr_non_campaign_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationpreference',
            name='mentions',
            field=models.BooleanField(default=True),
        ),
    ]
