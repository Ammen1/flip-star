"""Notification delivery, and the preferences that govern it.

Two things live here.

**Preferences.** ``NotificationPreference`` has existed since the first
release with per-type switches and a master push toggle, and until now no
code read it: every ``Notification`` row fanned out to FCM and Web Push
regardless of what the user had turned off. :func:`push_allowed` is what the
``post_save`` signal now consults before pushing.

The switch governs *push*, not the notification itself. Turning likes off
means a like stops buzzing the phone; it still appears in the in-app list,
because that list is the user's record of what happened to their account and
silently dropping rows from it would lose information rather than reduce
noise.

**System notifications.** Subscription activation, renewal and expiry, a
prize won or delivered, a withdrawal paid -- these are raised by the platform
about the user's own account and have no sender. :func:`notify_system`
creates them; ``Notification.sender`` is nullable for exactly this case.

Both entry points are deliberately best-effort: a notification that cannot be
written must never be the reason a subscription fails to activate or a prize
fails to pay. Callers are in the middle of doing something that matters more.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# Which preference switch governs which notification type.
#
# ``None`` means the type is always pushed. Moderation notices tell a user
# their content was removed or their account actioned -- consequences of an
# admin decision they cannot opt out of being told about. Everything a user
# can reasonably mute is mapped to a switch.
PREFERENCE_FIELD = {
    'like': 'likes',
    'comment': 'comments',
    'follow': 'follows',
    'mention': 'mentions',
    'gift': 'gifts',
    'moderation': None,
    'subscription_activated': 'system',
    'subscription_renewed': 'system',
    'subscription_expired': 'system',
    'prize_won': 'system',
    'prize_delivered': 'system',
    'withdrawal_paid': 'system',
}


def preferences_for(user):
    """The user's preference row, or ``None`` if there isn't one.

    A row is created by signal on registration, but accounts made before that
    signal existed -- and any created in a migration or a fixture -- may have
    none.
    """
    if user is None:
        return None
    try:
        from api.models import NotificationPreference

        return NotificationPreference.objects.filter(user=user).first()
    except Exception:  # pragma: no cover - defensive, DB unavailable
        logger.exception(
            'Could not read notification preferences for user=%s', getattr(user, 'id', None)
        )
        return None


def push_allowed(user, notification_type):
    """Whether a push for ``notification_type`` may be sent to ``user``.

    Absence of a preference row means *allow*: that is what the system did
    before preferences were read at all, and a missing row is a gap in our
    data rather than a statement by the user. An unrecognised type is also
    allowed -- a new type should be visible and then mapped, not silently
    swallowed here.
    """
    prefs = preferences_for(user)
    if prefs is None:
        return True

    # Master switch. Off means no push of any kind, including the types that
    # have no individual switch.
    if not getattr(prefs, 'push_notifications', True):
        return False

    field = PREFERENCE_FIELD.get(notification_type, None)
    if field is None:
        return True
    return bool(getattr(prefs, field, True))


def notify_system(recipient, notification_type, message, *, reel=None):
    """Create a senderless notification about the recipient's own account.

    Returns the ``Notification``, or ``None`` if it could not be written.
    Never raises: every caller is mid-way through something -- activating a
    subscription, paying out a prize -- that must not fail because of a
    notification.
    """
    if recipient is None:
        return None
    try:
        from api.models import Notification

        if notification_type not in Notification.SYSTEM_TYPES:
            raise ValueError(f'{notification_type!r} is not a system notification type')

        return Notification.objects.create(
            recipient=recipient,
            sender=None,
            notification_type=notification_type,
            reel=reel,
            message=message,
        )
    except Exception:
        logger.exception(
            'Could not create %s notification for user=%s',
            notification_type,
            getattr(recipient, 'id', None),
        )
        return None
