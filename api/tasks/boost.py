"""
Retiring boost campaigns once their time is up.

Nothing did this. A campaign was set ``status='active'`` when it started and
stayed that way for ever -- staging currently holds one that ended fourteen
hours ago, still marked active, still holding 442 unspent coins. There was no
task, no scheduled job, and no code path anywhere that moved a BoostCampaign
to ``completed``. (``api/tasks/leaderboards.py`` completes contest Campaigns,
which is a different model.)

Why that matters even though Trending is already safe
-----------------------------------------------------
The trending feeds re-check ``end_time`` in the query, so an expired campaign
gets no lift regardless of what its status says. Everything else that filters
on ``status='active'`` alone does not have that protection -- reporting,
the admin, and any future caller that reasonably trusts the field.

Leaving the flag wrong also leaves ``Reel.is_boosted`` and
``Reel.active_boost_campaign`` pointing at a finished campaign, so the post
keeps whatever badge or treatment the client gives a boosted post long after
the user stopped paying for it.

What this deliberately does NOT do
----------------------------------
It does not refund ``coins_remaining``.

Unspent budget on an expired campaign means impressions were bought and not
served, so a refund is arguably owed -- but that is a money decision with a
policy behind it (full refund? pro-rata? credit only?), and picking one here
would be inventing commercial terms. The amount is logged and left on the row
so it can be reconciled deliberately once someone decides. Silently moving
customer coins in either direction is the one thing this must not do on its
own initiative.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def expire_boost_campaigns():
    """Mark finished campaigns completed and clear the flags on their posts.

    Idempotent: only campaigns still marked active are touched, so a re-run
    right after one does nothing. Safe to schedule frequently.
    """
    from api.models.boost import BoostCampaign

    now = timezone.now()
    finished = BoostCampaign.objects.filter(status='active', end_time__lte=now).select_related(
        'reel'
    )

    completed = 0
    unspent_total = 0

    for campaign in finished:
        with transaction.atomic():
            # Re-read under a lock: a concurrent pacing check could be pausing
            # this same campaign, and two writers racing on `status` would
            # otherwise decide different outcomes.
            locked = (
                BoostCampaign.objects.select_for_update()
                .filter(pk=campaign.pk, status='active')
                .first()
            )
            if locked is None:
                continue

            unspent = locked.coins_remaining or 0

            # A guaranteed campaign that ran out of window before it ran out
            # of impressions did not deliver what it sold. Recording that as
            # 'completed' would make the ledger say the guarantee was
            # honoured -- the one thing this product must not claim falsely.
            shortfall = 0
            if locked.guaranteed_impressions:
                shortfall = max(0, locked.guaranteed_impressions - locked.impressions_served)

            locked.status = 'undelivered' if shortfall else 'completed'
            locked.save(update_fields=['status'])

            if shortfall:
                # Logged, not refunded: what is owed for an undelivered
                # guarantee is a commercial decision (BoostConfig carries a
                # refund_threshold_percent that nothing reads yet), and
                # moving coins on a guess is worse than leaving an accurate
                # record for somebody to act on.
                logger.warning(
                    '[BOOST EXPIRY] Campaign %s ended %s impressions short of its '
                    'guarantee of %s (served %s) on reel %s',
                    locked.pk,
                    shortfall,
                    locked.guaranteed_impressions,
                    locked.impressions_served,
                    locked.reel_id,
                )

            reel = locked.reel
            # Only clear the post's flags if THIS campaign is the one it
            # points at. A post may carry several campaigns over its life, and
            # clearing unconditionally would switch off a newer, live boost.
            if reel and getattr(reel, 'active_boost_campaign_id', None) == locked.pk:
                reel.is_boosted = False
                reel.active_boost_campaign = None
                reel.save(update_fields=['is_boosted', 'active_boost_campaign'])
            elif reel and reel.is_boosted and not _has_live_campaign(reel, now):
                # Flag left set by an older code path with no campaign pointer.
                reel.is_boosted = False
                reel.save(update_fields=['is_boosted'])

            completed += 1
            unspent_total += unspent

            if unspent > 0:
                # Logged rather than refunded -- see the module docstring.
                logger.info(
                    '[BOOST EXPIRY] Campaign %s on reel %s completed with %s coins unspent',
                    locked.pk,
                    reel.pk if reel else None,
                    unspent,
                )

    if completed:
        logger.info(
            '[BOOST EXPIRY] Completed %s campaign(s), %s coins unspent in total',
            completed,
            unspent_total,
        )

    return f'Completed {completed} expired boost campaign(s), {unspent_total} coins unspent'


def _has_live_campaign(reel, now):
    """True when some other campaign on this post is still running."""
    from api.models.boost import BoostCampaign

    return BoostCampaign.objects.filter(
        reel=reel,
        status='active',
        end_time__gt=now,
        coins_remaining__gt=0,
    ).exists()
