"""Prize delivery tracking on WinnerGiftTransaction.

Adds what the prize-management requirement asks a delivery to record and the
row did not carry: which campaign it was won in, how many delivery attempts
have been made, when it must be delivered by, when it actually was, and the
idempotency key that stops a winner being paid twice.

The backfill below only fills `delivered_at` for rows already marked
'success'. It uses `updated_at`, which for those rows is the moment
mark_success wrote them -- the best record of delivery that exists. Rows in
any other state are left alone: guessing a delivery time for a prize that
may never have been delivered would put a false settlement in the ledger.
"""

import django.db.models.deletion
from django.db import migrations, models


def backfill_delivered_at(apps, schema_editor):
    WinnerGiftTransaction = apps.get_model('api', 'WinnerGiftTransaction')
    WinnerGiftTransaction.objects.filter(
        status='success', delivered_at__isnull=True
    ).update(delivered_at=models.F('updated_at'))


def clear_delivered_at(apps, schema_editor):
    """Reverse: the column is dropped straight after, so this only has to
    leave the table in the state the forward migration found it."""
    WinnerGiftTransaction = apps.get_model('api', 'WinnerGiftTransaction')
    WinnerGiftTransaction.objects.update(delivered_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0136_engagement_costs'),
    ]

    operations = [
        migrations.AddField(
            model_name='winnergifttransaction',
            name='attempt_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='winnergifttransaction',
            name='campaign',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='prize_deliveries', to='api.campaign'),
        ),
        migrations.AddField(
            model_name='winnergifttransaction',
            name='deadline_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='winnergifttransaction',
            name='delivered_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='winnergifttransaction',
            name='idempotency_key',
            field=models.CharField(blank=True, max_length=200, null=True, unique=True),
        ),
        migrations.AddIndex(
            model_name='winnergifttransaction',
            index=models.Index(fields=['campaign', 'winner_type'], name='api_winnerg_campaig_d2a56a_idx'),
        ),
        migrations.AddIndex(
            model_name='winnergifttransaction',
            index=models.Index(fields=['status', 'deadline_at'], name='api_winnerg_status_3e6178_idx'),
        ),
        migrations.RunPython(backfill_delivered_at, clear_delivered_at),
    ]
