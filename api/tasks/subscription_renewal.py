"""
Renewing a lapsed short-code subscription off the request path.

Queued by the subscription status endpoint, which must answer immediately and
never wait on TIMWE. The rules -- once per period, never after a pending or
ambiguous attempt, renew only on confirmed success -- live in
api/services/subscription_renewal.py; this is only the carrier.

No retries, on purpose. A failed charge is not retried automatically, and an
ambiguous one must not be. If the worker dies mid-charge, ``acks_late``
redelivers the task; the committed PENDING row is found and nothing is sent a
second time.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name='api.tasks.subscription_renewal.renew_expired_subscription',
    acks_late=True,
    reject_on_worker_lost=True,
)
def renew_expired_subscription(user_id):
    """Check one user's short-code subscription and renew it if it is due."""
    from django.contrib.auth.models import User

    from api.services.subscription_renewal import check_and_renew_subscription

    user = User.objects.filter(pk=user_id).select_related('profile').first()
    if user is None:
        logger.warning('SUBSCRIPTION_RENEWAL_NO_USER', extra={'user_id': user_id})
        return 'missing'
    return check_and_renew_subscription(user).state
