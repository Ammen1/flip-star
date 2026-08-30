"""
Whether a user may perform a subscriber-only action.

One query, one answer. ``UserSubscriptionStatusView`` builds the full status
payload for the client; this module answers the single yes/no question the
write endpoints need, using the same definition of "active" so the two can
never disagree:

* a ``SubscriptionPlan`` with ``status='active'`` whose ``end_date`` is still
  in the future, or
* a legacy ``Subscription`` row that has not yet expired.

Kept separate from the view so posting endpoints do not have to import view
code, and so the rule has somewhere to be tested on its own.
"""

from django.utils import timezone

SUBSCRIPTION_REQUIRED_CODE = 'SUBSCRIPTION_REQUIRED'

SUBSCRIPTION_REQUIRED_MESSAGE = 'An active subscription is required to post videos.'


def has_active_subscription(user):
    """True when `user` currently holds an active subscription."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False

    # Imported here: this module is pulled in by views at request time, and a
    # module-level model import would run before the app registry is ready.
    from api.models import Subscription
    from api.models.subscription import SubscriptionPlan

    now = timezone.now()

    if SubscriptionPlan.objects.filter(
        user=user, status='active', end_date__gt=now
    ).exists():
        return True

    return Subscription.objects.filter(user=user, expires_at__gt=now).exists()


def subscription_required_payload(message=None):
    """The body every endpoint returns when it refuses for want of a subscription.

    A single shape means the client can branch on ``code`` instead of matching
    error prose, which is what lets the post page keep the user's draft and
    open the activation prompt rather than showing a generic failure.
    """
    return {
        'success': False,
        'code': SUBSCRIPTION_REQUIRED_CODE,
        'message': message or SUBSCRIPTION_REQUIRED_MESSAGE,
    }
