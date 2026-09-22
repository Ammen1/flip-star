"""
Give a coin transaction somewhere to record that its payment failed.

Until now there was only ``is_successful``, which is False both for a payment
still waiting for its callback and for one telebirr refused. Nothing could
tell those apart, so nothing could tell a customer their payment had failed --
they were shown "we have not received a confirmation yet" for a payment that
was never going to arrive, or, through the SuperApp, a green tick.

Columns only. The backfill that gives them their values is 0129, and the
split is not cosmetic: PostgreSQL refuses to build an index on a table
with pending trigger events, and Django defers the index for a db_index
field to the end of the migration -- after any RunPython in the same
migration has updated rows and queued foreign-key trigger events. Doing
both here failed staging with
``cannot CREATE INDEX "coin_transactions" because it has pending trigger
events``. SQLite has no such rule, so the test suite never saw it.

Existing rows are read as what they already meant (in 0129):

* ``is_successful`` → SUCCESS.
* not successful, and the webhook wrote a "Failed ..." description → FAILED,
  which is the only record the old code kept of a refusal.
* everything else not successful → PENDING, which is what an uncredited row
  with no failure written on it is. It is also the safe reading: PENDING
  grants nothing and shows nothing as succeeded.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0125_ondemand_coin_allocation'),
    ]

    operations = [
        migrations.AddField(
            model_name='cointransaction',
            name='payment_reason',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='cointransaction',
            name='provider_conversation_id',
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.AddField(
            model_name='cointransaction',
            name='payment_state',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('SUCCESS', 'Success'),
                    ('FAILED', 'Failed'),
                    ('CANCELLED', 'Cancelled'),
                ],
                db_index=True,
                default='SUCCESS',
                help_text='Authoritative payment state; only SUCCESS may move a balance',
                max_length=16,
            ),
        ),
    ]
