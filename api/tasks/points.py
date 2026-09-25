"""
The 180-day points sweep.

Points not withdrawn or converted within 180 days of inactivity are lost.
Coins are not touched -- see api/services/points_expiry.py for why that
sentence is load-bearing.

Daily, because the rule is measured in days and a sweep that runs more often
would only re-examine the same accounts. Each user is decided and written
under their own lock, so a long run cannot hold the table, and a run that
dies partway leaves the accounts it already handled correctly done rather
than half-done.
"""

import logging

from celery import shared_task

from api.services import points_expiry

logger = logging.getLogger(__name__)

#: Accounts examined per run. The sweep is idempotent, so whatever is not
#: reached today is reached tomorrow.
BATCH_SIZE = 500


@shared_task
def expire_inactive_points():
    """Take the points of accounts inactive for 180 days."""
    examined = expired_users = expired_points = 0

    for profile in points_expiry.candidates()[:BATCH_SIZE]:
        examined += 1
        try:
            taken = points_expiry.expire_points_for(profile.user)
        except Exception:
            # One bad account must not strand the rest of the sweep.
            logger.exception('POINTS_EXPIRY_FAILED user=%s', profile.user_id)
            continue

        if taken:
            expired_users += 1
            expired_points += taken

    logger.info(
        'POINTS_EXPIRY_RUN examined=%s expired_users=%s expired_points=%s after_days=%s',
        examined,
        expired_users,
        expired_points,
        points_expiry.INACTIVITY_DAYS,
    )
    return f'Examined {examined}, expired {expired_points} points from {expired_users} accounts'
