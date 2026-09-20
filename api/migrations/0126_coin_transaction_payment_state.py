"""
Give a coin transaction somewhere to record that its payment failed.

Until now there was only ``is_successful``, which is False both for a payment
still waiting for its callback and for one telebirr refused. Nothing could
tell those apart, so nothing could tell a customer their payment had failed --
they were shown "we have not received a confirmation yet" for a payment that
was never going to arrive, or, through the SuperApp, a green tick.

Existing rows are read as what they already meant:

* ``is_successful`` → SUCCESS.
* not successful, and the webhook wrote a "Failed ..." description → FAILED,
  which is the only record the old code kept of a refusal.
* everything else not successful → PENDING, which is what an uncredited row
  with no failure written on it is. It is also the safe reading: PENDING
  grants nothing and shows nothing as succeeded.
"""

from django.db import migrations, models


def set_state_from_history(apps, schema_editor):
    CoinTransaction = apps.get_model('api', 'CoinTransaction')

    CoinTransaction.objects.filter(is_successful=True).update(payment_state='SUCCESS')

    # The webhook's own wording is the only surviving evidence of a refusal:
    # api/views/wallet.py wrote 'Failed USSD Push payment: ...' /
    # 'Failed Telebirr payment: ...' onto the row and left it otherwise
    # indistinguishable from one still in flight.
    CoinTransaction.objects.filter(is_successful=False, description__startswith='Failed').update(
        payment_state='FAILED'
    )

    CoinTransaction.objects.filter(is_successful=False).exclude(
        description__startswith='Failed'
    ).update(payment_state='PENDING')

    # Rows that have not settled still hold the conversation id in
    # payment_reference, so the correlation key can be recovered for exactly
    # the payments a client might still be waiting on. Settled rows had theirs
    # overwritten by the provider's transaction id and it is simply gone --
    # nothing is polling those.
    for row in CoinTransaction.objects.filter(
        is_successful=False, payment_method__in=('telebirr', 'telebirr_ussd')
    ).exclude(payment_reference=''):
        row.provider_conversation_id = row.payment_reference
        row.save(update_fields=['provider_conversation_id'])


def unset_state(apps, schema_editor):
    """Nothing to undo: the columns go with the field."""


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
        migrations.RunPython(set_state_from_history, unset_state),
    ]
