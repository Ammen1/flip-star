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

from django.db import models
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

    if SubscriptionPlan.objects.filter(user=user, status='active', end_date__gt=now).exists():
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


ALREADY_SUBSCRIBED_CODE = 'ALREADY_SUBSCRIBED'


def active_subscription_for(user=None, phone_number=None):
    """The caller's live subscription, or None.

    Resolves by `user` when signed in, otherwise by `phone_number` -- which is
    what the telebirr SuperApp flow has: the page there is not authenticated
    (``/subscriptions/`` 401s for it), so the phone is the only identity
    available before the OTP login that follows payment.

    Returns the ``SubscriptionPlan`` so callers can describe it.
    """
    from api.models.subscription import SubscriptionPlan

    now = timezone.now()
    qs = SubscriptionPlan.objects.filter(status='active').select_related('tier')

    # An `end_date` in the past is not an active subscription however the
    # status column reads -- renewals that failed can leave the two disagreeing.
    qs = qs.filter(models.Q(end_date__isnull=True) | models.Q(end_date__gt=now))

    if user is not None and getattr(user, 'is_authenticated', False):
        return qs.filter(user=user).order_by('-start_date').first()

    if phone_number:
        from api.models import UserProfile

        profile = UserProfile.objects.filter(phone_number=phone_number).first()
        if profile:
            return qs.filter(user=profile.user).order_by('-start_date').first()

    return None


def subscription_summary(plan):
    """A small, non-sensitive description of an active subscription.

    Safe to return to the unauthenticated SuperApp page: it names the plan the
    caller just tried to buy again, and carries no account identifiers.
    """
    if plan is None:
        return None
    tier = getattr(plan, 'tier', None)
    return {
        'tier_name': getattr(tier, 'name', None),
        'duration_type': getattr(plan, 'duration_type', None),
        'start_date': plan.start_date.isoformat() if plan.start_date else None,
        'end_date': plan.end_date.isoformat() if plan.end_date else None,
    }


def already_subscribed_payload(plan, message=None):
    """The refusal returned when someone tries to subscribe twice.

    Carries a stable ``code`` so the client shows the existing subscription
    instead of a generic failure -- and, crucially, so a second charge never
    starts.
    """
    return {
        'success': False,
        'code': ALREADY_SUBSCRIBED_CODE,
        'error': message or 'You already have an active subscription.',
        'subscription': subscription_summary(plan),
    }
