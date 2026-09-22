"""The daily subscription gift sweep.

A subscriber's gift coins arrive a day at a time across their plan
(api/services/subscription_daily_gift.py). This is what pays them.

Idempotent by construction: every day of every plan has its own key on the
coin ledger, so running twice in a day, or catching up after the worker was
down, pays each day exactly once.
"""

from celery import shared_task


@shared_task(name='api.tasks.grant_daily_subscription_gifts')
def grant_daily_subscription_gifts():
    from api.services.subscription_daily_gift import sweep

    return sweep()
