"""Web Push delivery, off the request path.

Audit finding H-07. ``send_web_push_to_user`` used to be called straight from
the ``Notification`` post_save signal, with the comment "synchronous but cheap".
It was not cheap: it makes one outbound HTTP request per subscription, to a
destination the subscriber supplied, and it ran inside whichever thread created
the notification -- ordinarily an API request thread. A push service that
accepted the connection and never answered held that thread, and the
``except Exception`` around the call could not help, because a hang is not an
exception.

The FCM sibling in the same signal already went through Celery
(``send_push_notification.delay(...)``); this brings web push into line with it.
A hard time limit is set here rather than left to the global default, since
audit finding H-06 records that no task had one.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

#: Five subscriptions x a 10s per-request timeout, plus room to spare. The soft
#: limit raises inside the task so the count delivered so far still gets logged;
#: the hard limit is the backstop.
_SOFT_TIME_LIMIT = 60
_TIME_LIMIT = 90


@shared_task(soft_time_limit=_SOFT_TIME_LIMIT, time_limit=_TIME_LIMIT)
def send_web_push(user_id: int, payload: dict) -> int:
    """Deliver ``payload`` to every Web Push subscription ``user_id`` has.

    Returns the number of subscriptions delivered to. Never raises: a push that
    cannot be delivered must not retry a notification that is already recorded,
    and there is nothing for a caller to do with the failure.
    """
    from api.integrations.push.webpush import send_web_push_to_user

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.debug('Web push skipped: user %s no longer exists', user_id)
        return 0

    try:
        return send_web_push_to_user(user, payload)
    except Exception:
        logger.warning(
            'Web push delivery failed for user %s',
            user_id,
            exc_info=True,
            extra={'operation': 'web_push_send', 'result': 'error'},
        )
        return 0
