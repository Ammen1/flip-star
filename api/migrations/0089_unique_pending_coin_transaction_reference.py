# Concurrency audit, Finding #4 (see docs/concurrency-audit follow-up).
#
# The originally recommended constraint was a plain unique index on
# (payment_method, payment_reference) for non-empty references. That would
# NOT be safe to add as-is: api/views/wallet.py::telebirr_callback finalizes
# a successful purchase by (a) flipping the existing pending CoinTransaction
# to is_successful=True with payment_reference=telebirr_transaction_id, AND
# (b) calling UserCoinBalance.add_purchased(..., payment_reference=telebirr_
# transaction_id, ...), which creates a SECOND, separate CoinTransaction row
# (see UserCoinBalance.add_purchased in api/models/contest.py) carrying the
# exact same payment_method/payment_reference pair as its own ledger entry.
# That is by design (one row is the payment-webhook audit record, the other
# is the balance ledger entry) -- a plain unique constraint across all rows
# would make every successful Telebirr purchase raise IntegrityError inside
# the webhook handler.
#
# The actual invariant that needs protecting is narrower: telebirr_callback
# looks up the PENDING record with
#   CoinTransaction.objects.select_for_update().get(
#       payment_reference=out_trade_no, payment_method='telebirr', is_successful=False)
# which assumes at most one match. Two pending rows sharing a reference
# would make that .get() raise MultipleObjectsReturned. Scoping the unique
# constraint to is_successful=False rows protects exactly that invariant
# without touching the legitimate two-rows-per-completed-purchase pattern.
#
# Verified against the local dev database (13 total coin_transactions rows,
# 0 with a non-empty payment_reference) -- no existing duplicates in the
# only data available in this environment. This has NOT been verified
# against production data; run the equivalent duplicate-check query there
# before relying on this constraint in production:
#
#   SELECT payment_method, payment_reference, COUNT(*)
#   FROM coin_transactions
#   WHERE payment_reference != '' AND is_successful = false
#   GROUP BY payment_method, payment_reference
#   HAVING COUNT(*) > 1;

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0088_direct_debit_transient_statuses'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='cointransaction',
            constraint=models.UniqueConstraint(
                fields=['payment_method', 'payment_reference'],
                condition=models.Q(payment_reference__gt='') & models.Q(is_successful=False),
                name='unique_pending_coin_transaction_payment_reference',
            ),
        ),
    ]
