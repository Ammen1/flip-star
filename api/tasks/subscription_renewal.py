"""
Renewing lapsed short-code subscriptions off the request path.

Two tasks. ``sweep_expired_subscriptions`` runs hourly on celery beat and
queues every lapsed airtime subscriber who is due a renewal -- the first try
when a period runs out, and the next one after TIMWE refused the last (too
little airtime, say). ``renew_expired_subscription`` renews one user; the sweep
queues it, and so does the subscription status endpoint, which must answer
immediately and never wait on TIMWE.

The rules -- one live charge per period, never after a pending or ambiguous
attempt, a refused one tried again only after TIMWE_RENEWAL_RETRY_MINUTES,
renew only on confirmed success -- live in api/services/subscription_renewal.py;
these are only the carriers.

Neither task retries itself. A retry is a new attempt the next sweep makes,
never a re-run of one whose outcome is unknown. If the worker dies mid-charge,
``acks_late`` redelivers the task; the committed PENDING row is found and
nothing is sent a second time.
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


@shared_task(name='api.tasks.subscription_renewal.sweep_expired_subscriptions')
def sweep_expired_subscriptions():
    """Hourly: queue a renewal for every lapsed airtime subscription that is due one.

    A no-op unless TIMWE_CHARGING_ENABLED and TIMWE_SUBSCRIPTION_RENEWAL_ENABLED
    are both on and chargeAmount is configured.
    """
    from api.services.subscription_renewal import sweep_due_renewals

    return sweep_due_renewals()
