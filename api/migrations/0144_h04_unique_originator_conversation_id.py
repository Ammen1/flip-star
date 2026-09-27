"""Audit finding H-04: make the payout correlation key unique in the database.

Three models carry ``originator_conversation_id`` and all three correlate a
Telebirr result callback back to the row it settles:

    WithdrawalRequest      api/views/wallet.py         -- pays a user out
    B2CPaymentTransaction  api/views/direct_debit.py   -- standalone payout
    DirectDebitMandate     api/views/direct_debit.py:619 -- mandate result

Uniqueness was a property of the id generator and nothing else. Nothing in the
database stopped two rows sharing a key, and the webhook resolves with
``.filter(...).first()`` -- so if two ever did, one callback would settle
whichever row came back first and the other would be left behind. On
``B2CPaymentTransaction`` there was no index at all, so that lookup was a
sequential scan of the payout table on the path that decides whether money was
sent.

The constraints are **partial**. The column is ``blank=True``: a withdrawal
exists before its B2C call is made, so ``''`` is a legitimate value and appears
on many rows. ``condition=~Q(field='')`` is what lets uniqueness coexist with
them, and it costs nothing at lookup time because the webhook returns early on a
missing ``OriginatorConversationID`` and therefore never searches for ``''``.

A duplicate check runs first. Adding a unique index to a table that already
violates it fails with a message naming an index, not the rows -- so this raises
something actionable instead, and it is a no-op on a database that is already
clean (including every fresh one, where all three tables are empty).
"""

from django.db import migrations, models


def _check_for_duplicates(apps, schema_editor):
    """Refuse to proceed if any of the three tables already has a duplicate key.

    Reverse is a no-op: removing the constraints cannot reintroduce duplicates.
    """
    from django.db.models import Count

    targets = [
        ('api', 'WithdrawalRequest'),
        ('api', 'B2CPaymentTransaction'),
        ('api', 'DirectDebitMandate'),
    ]

    problems = []
    for app_label, model_name in targets:
        model = apps.get_model(app_label, model_name)
        duplicated = (
            model.objects.exclude(originator_conversation_id='')
            .values('originator_conversation_id')
            .annotate(n=Count('id'))
            .filter(n__gt=1)
            .order_by('-n')
        )
        for row in duplicated[:20]:
            problems.append(
                '  %s: %r appears %d times'
                % (model_name, row['originator_conversation_id'], row['n'])
            )

    if problems:
        raise RuntimeError(
            'Cannot add the H-04 uniqueness constraints: duplicate '
            'originator_conversation_id values already exist.\n'
            + '\n'.join(problems)
            + '\n\nEach duplicate is a payout whose result callback could have settled '
            'the wrong row, so these need looking at rather than deleting blind. '
            'Reconcile them against Telebirr first, then re-run this migration.'
        )


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0143_backfill_tier_charge_service_ids'),
    ]

    operations = [
        migrations.RunPython(_check_for_duplicates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='b2cpaymenttransaction',
            constraint=models.UniqueConstraint(
                condition=models.Q(('originator_conversation_id', ''), _negated=True),
                fields=('originator_conversation_id',),
                name='uniq_b2c_originator_conversation_id',
            ),
        ),
        migrations.AddConstraint(
            model_name='directdebitmandate',
            constraint=models.UniqueConstraint(
                condition=models.Q(('originator_conversation_id', ''), _negated=True),
                fields=('originator_conversation_id',),
                name='uniq_mandate_originator_conversation_id',
            ),
        ),
        migrations.AddConstraint(
            model_name='withdrawalrequest',
            constraint=models.UniqueConstraint(
                condition=models.Q(('originator_conversation_id', ''), _negated=True),
                fields=('originator_conversation_id',),
                name='uniq_withdrawal_originator_conversation_id',
            ),
        ),
    ]
