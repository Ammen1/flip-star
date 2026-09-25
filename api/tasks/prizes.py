"""
Delivering won prizes, and noticing when delivery is not happening.

Why this exists
---------------
Winner selection recorded what each winner was owed and then stopped.
``award_all`` wrote the prize rows and nothing ever sent them, so every
prize sat 'pending' until an operator opened the admin and pressed a button.
The requirement promises delivery within 10 days (20 for the Grand Final),
and a promise whose only enforcement is somebody remembering is one that
gets missed.

These two tasks close that: one delivers, the other reports on what
delivery could not fix on its own.

What is deliberately not retried
--------------------------------
A prize in 'processing' is never re-sent. That state means Telebirr has the
instruction and the confirmation has not come back, and sending another is
precisely how one winner gets paid twice. When a payout stays there it is
reported as stuck, not retried -- the fix is finding out why the callback
did not arrive, which is not something a retry can do.
"""

import logging

from celery import shared_task

from api.services.prize_delivery import (
    MAX_DELIVERY_ATTEMPTS,
    abandoned_deliveries,
    deliver,
    deliverable,
    overdue_deliveries,
    skipped_deliveries,
    stuck_deliveries,
)

logger = logging.getLogger(__name__)

#: Deliveries attempted per run. A cap so one run cannot spend an unbounded
#: time in external calls; the next run picks up the remainder.
BATCH_SIZE = 50


@shared_task
def deliver_pending_prizes():
    """Send prizes that are owed and not yet delivered.

    Pending ones and failed ones still under the attempt cap. Every guard
    lives in the delivery service, so this cannot pay anybody twice however
    often it runs or however many runs overlap: an already-settled or
    in-flight prize is refused there, not here.
    """
    results = {'delivered': 0, 'initiated': 0, 'failed': 0, 'skipped': 0}

    prizes = deliverable().select_related('winner', 'campaign').order_by('deadline_at')[:BATCH_SIZE]

    for prize in prizes:
        try:
            ok, message = deliver(prize)
        except Exception:
            logger.exception('PRIZE_DELIVERY_RUN_FAILED prize=%s', prize.pk)
            results['failed'] += 1
            continue

        if not ok:
            if 'already' in message or 'in progress' in message:
                results['skipped'] += 1
            else:
                results['failed'] += 1
            continue

        prize.refresh_from_db()
        # Data provisioning settles in the same call; a cash payout only
        # reaches 'processing' and is completed by the B2C webhook.
        if prize.status == 'success':
            results['delivered'] += 1
        else:
            results['initiated'] += 1

    logger.info(
        'PRIZE_DELIVERY_RUN delivered=%s initiated=%s failed=%s skipped=%s',
        results['delivered'],
        results['initiated'],
        results['failed'],
        results['skipped'],
    )
    return (
        f'Delivered {results["delivered"]}, initiated {results["initiated"]}, '
        f'failed {results["failed"]}, skipped {results["skipped"]}'
    )


@shared_task
def report_prize_delivery_problems():
    """Log what delivery cannot fix by itself.

    Three kinds, each needing a person rather than another attempt:

    * **overdue** -- past the promised deadline and still not delivered;
    * **stuck** -- Telebirr accepted a payout and never confirmed it, which
      no retry can resolve because there is no B2C query API to ask; and
    * **abandoned** -- failed as many times as the scheduler will try.

    Reported rather than acted on: each one means something is wrong outside
    this code, and a task that tried to paper over it would only hide how
    long it had been wrong.
    """
    overdue = list(overdue_deliveries().select_related('winner'))
    stuck = list(stuck_deliveries().select_related('winner'))
    abandoned = list(abandoned_deliveries().select_related('winner'))
    skipped = list(skipped_deliveries().select_related('winner'))

    for prize in overdue:
        logger.warning(
            'PRIZE_OVERDUE prize=%s tier=%s status=%s deadline=%s attempts=%s',
            prize.pk,
            prize.winner_type,
            prize.status,
            prize.deadline_at,
            prize.attempt_count,
        )

    for prize in stuck:
        logger.warning(
            'PRIZE_PAYOUT_UNCONFIRMED prize=%s tier=%s since=%s conversation=%s',
            prize.pk,
            prize.winner_type,
            prize.updated_at,
            prize.conversation_id or '(none)',
        )

    for prize in abandoned:
        logger.error(
            'PRIZE_DELIVERY_ABANDONED prize=%s tier=%s attempts=%s reason=%s',
            prize.pk,
            prize.winner_type,
            prize.attempt_count,
            prize.error_message[:200],
        )

    for prize in skipped:
        logger.warning(
            'PRIZE_UNDELIVERABLE prize=%s tier=%s amount=%s reason=%s',
            prize.pk,
            prize.winner_type,
            prize.amount,
            prize.error_message[:200],
        )

    _report_missing_data_package()

    logger.info(
        'PRIZE_DELIVERY_HEALTH overdue=%s unconfirmed=%s abandoned=%s undeliverable=%s '
        'max_attempts=%s',
        len(overdue),
        len(stuck),
        len(abandoned),
        len(skipped),
        MAX_DELIVERY_ATTEMPTS,
    )
    return (
        f'{len(overdue)} overdue, {len(stuck)} unconfirmed, '
        f'{len(abandoned)} abandoned, {len(skipped)} undeliverable'
    )


def _report_missing_data_package():
    """Say so when data prizes are waiting and no package is configured.

    `manage.py check` reports the missing OfferingId at deploy time, which is
    the right moment to notice it. This is the other moment: when winners are
    actually waiting for a bundle that cannot be sent. Separating the two
    matters because the config can be removed long after deployment, and
    because a warning tied to a real count of waiting winners is the one an
    operator acts on.
    """
    from django.conf import settings

    from api.models.gift import WinnerGiftTransaction
    from api.services.prize_structure import CRM

    offering = getattr(settings, 'DATA_PRIZE_OFFERING_ID', '') or getattr(
        settings, 'CRM_OFFERING_ID', ''
    )
    if offering:
        return

    waiting = WinnerGiftTransaction.objects.filter(
        payment_method=CRM
    ).exclude(status='success').count()
    if not waiting:
        return

    logger.error(
        'PRIZE_DATA_PACKAGE_UNCONFIGURED waiting=%s -- DATA_PRIZE_OFFERING_ID is unset, '
        'so every data prize fails with "No data package configured"',
        waiting,
    )
