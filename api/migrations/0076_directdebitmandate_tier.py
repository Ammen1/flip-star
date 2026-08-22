from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0075_walletconfig_withdrawal_points_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='directdebitmandate',
            name='tier',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='direct_debit_mandates',
                to='api.subscriptiontier',
                help_text='Subscription tier this mandate was created for',
            ),
        ),
    ]
