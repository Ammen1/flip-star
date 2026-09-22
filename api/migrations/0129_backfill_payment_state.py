"""Give the payment-state columns 0126 added their values.

Split out of 0126 deliberately. PostgreSQL refuses ``CREATE INDEX`` on a table
that has pending trigger events, and Django defers the index for a
``db_index`` field to the end of the migration that adds it -- so a RunPython
in that same migration queues foreign-key trigger events and the deferred
index creation then fails:

    cannot CREATE INDEX "coin_transactions" because it has pending trigger
    events

Each migration runs in its own transaction, so by the time this one updates
rows, 0126's index already exists and is committed. SQLite does not have this
rule, which is why only staging's PostgreSQL caught it.
"""

from django.db import migrations


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
        ('api', '0128_charge_gift_amounts_by_plan_type'),
    ]

    operations = [
        migrations.RunPython(set_state_from_history, unset_state),
    ]
