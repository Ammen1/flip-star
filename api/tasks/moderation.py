"""Reporting the campaign moderation backlog.

Campaign entries queue as ``pending`` and only an admin opening the page
clears them. Eligibility counts pending entries -- deliberately, so a
subscriber is not penalised for a backlog they did not cause -- which means
an unreviewed entry can carry someone to a prize.

This task does not moderate and does not block anything. It makes the
backlog audible on a schedule, in the same shape the prize sweep reports
overdue deliveries, so that "nobody has looked at this campaign in two days"
is something the logs say rather than something discovered after a winner
is announced.
"""

import logging

from celery import shared_task

from api.services.moderation_queue import (
    CRITICAL_AFTER_HOURS,
    STALE_AFTER_HOURS,
    per_campaign_report,
    queue_report,
)

logger = logging.getLogger(__name__)


@shared_task(name='api.tasks.report_moderation_backlog')
def report_moderation_backlog():
    """Log the pending moderation queue, overall and per campaign.

    Returns the overall summary so a caller -- a health check, a test -- can
    read it without going through the logs.
    """
    overall = queue_report()

    if not overall['pending']:
        logger.info('MODERATION_QUEUE_EMPTY')
        return overall

    log = logger.warning if overall['stale'] else logger.info
    log(
        'MODERATION_QUEUE pending=%s stale=%s critical=%s oldest_hours=%s '
        'stale_after=%sh critical_after=%sh',
        overall['pending'],
        overall['stale'],
        overall['critical'],
        overall['oldest_hours'],
        STALE_AFTER_HOURS,
        CRITICAL_AFTER_HOURS,
    )

    # Per campaign, because one neglected campaign inside an otherwise
    # healthy queue is exactly what the total hides -- and it is the
    # campaign, not the queue, that awards a prize.
    for campaign_id, report in per_campaign_report().items():
        if not report['stale']:
            continue
        logger.warning(
            'MODERATION_BACKLOG campaign=%s pending=%s stale=%s critical=%s oldest_hours=%s',
            campaign_id,
            report['pending'],
            report['stale'],
            report['critical'],
            report['oldest_hours'],
        )

    if overall['critical']:
        logger.error(
            'MODERATION_QUEUE_CRITICAL entries=%s waiting over %sh; '
            'unreviewed entries count towards eligibility and may decide a winner',
            overall['critical'],
            CRITICAL_AFTER_HOURS,
        )

    return overall
