"""
Whether a user may perform a subscriber-only action.

One query, one answer. ``UserSubscriptionStatusView`` builds the full status
payload for the client; this module answers the single yes/no question the
write endpoints need, using the same definition of "active" so the two can
never disagree:

* a ``SubscriptionPlan`` with ``status='active'`` whose ``end_date`` is either
    open-ended or still in the future, or
* a legacy ``Subscription`` row that has not yet expired.

Kept separate from the view so posting endpoints do not have to import view
code, and so the rule has somewhere to be tested on its own.
"""

from datetime import timedelta

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

    if (
        SubscriptionPlan.objects.filter(
            user=user,
            status='active',
        )
        .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gt=now))
        .exists()
    ):
        return True

    return Subscription.objects.filter(user=user, expires_at__gt=now).exists()


#: What each subscriber-only action is called when refusing it.
#:
#: Non-subscribers may sign up, sign in, browse and view. Everything that
#: *contributes* -- posting, liking, sharing, commenting, entering a campaign
#: -- needs a plan. Spelled out per action because "an active subscription is
#: required to post videos" shown to somebody who tapped Like is the kind of
#: message that makes people think the app is broken.
SUBSCRIBER_ACTIONS = {
    'post': 'An active subscription is required to post.',
    'video': SUBSCRIPTION_REQUIRED_MESSAGE,
    'like': 'An active subscription is required to like posts.',
    'share': 'An active subscription is required to share posts.',
    'comment': 'An active subscription is required to comment.',
    'campaign': 'An active subscription is required to enter campaigns.',
    'gift': 'An active subscription is required to send gifts.',
    'boost': 'An active subscription is required to boost posts.',
}


def subscriber_action_refusal(user, action):
    """The refusal body for a subscriber-only action, or None if allowed.

    Coins are not the gate. A new account is given a welcome bonus
    (WalletConfig.welcome_bonus, 100 by default), so a non-subscriber has
    coins to spend and the engagement charge alone let them like, share and
    comment freely -- the charge prices an action, it does not decide who may
    take it.

    Deliberately not a boolean: the caller should not be inventing its own
    wording for a rule defined here, and the ``code`` is what the client
    branches on to open the subscribe prompt instead of showing a generic
    failure.
    """
    if has_active_subscription(user):
        return None

    return {
        'success': False,
        'code': SUBSCRIPTION_REQUIRED_CODE,
        'message': SUBSCRIBER_ACTIONS.get(action, SUBSCRIBER_ACTIONS['post']),
        'error': SUBSCRIBER_ACTIONS.get(action, SUBSCRIBER_ACTIONS['post']),
        'action': action,
    }


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


#: Attached to a sign-in response when the account has no active plan.
#:
#: The token is still issued. The client reads this flag and holds the user on
#: the subscribe screen instead of the feed -- which keeps the in-app renew
#: path working, and keeps a subscriber whose telebirr callback is merely late
#: from being locked out of an app they have paid for. Every contributing
#: action is already refused server-side by subscriber_action_refusal(), so an
#: issued token grants nothing a non-subscriber should not have.
LOGIN_REQUIRES_SUBSCRIPTION_CODE = 'SUBSCRIPTION_REQUIRED_TO_CONTINUE'


def resubscribe_instruction():
    """How to subscribe again by SMS: 'Send 1 to 9286 for Daily, ...'.

    Built from the live tiers rather than hard-coded, because the keyword and
    the short code both come from what the aggregator is configured to
    recognise -- the same source the cancellation SMS quotes. A hard-coded
    sentence here would drift from that SMS the first time a tier changes.
    """
    from django.conf import settings

    from api.models.subscription import SubscriptionTier
    from api.services.sms_subscription import SUBSCRIBE_KEYWORDS

    default_code = getattr(settings, 'SMS_SHORT_CODE', '9286')
    parts = []
    for duration, keyword in SUBSCRIBE_KEYWORDS.items():
        tier = SubscriptionTier.objects.filter(
            duration_type=duration, is_active=True
        ).first()
        if tier is None:
            continue
        parts.append(f'{keyword} to {tier.short_code or default_code} for {tier.name}')

    if not parts:
        # No tier is provisioned. Say something true rather than an empty
        # instruction that reads as a broken screen.
        return f'Send 1, 2 or 3 to {default_code} to subscribe.'
    return 'Send ' + ', or '.join(parts) + '.'


def has_ever_subscribed(user):
    """True when this account has held a plan before, active or not.

    Distinguishes "you were unsubscribed" from "you have never subscribed".
    Telling somebody they were unsubscribed when they never subscribed is the
    kind of wrong detail that makes people think their payment was lost.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return False

    from api.models import Subscription
    from api.models.subscription import SubscriptionPlan

    return (
        SubscriptionPlan.objects.filter(user=user).exists()
        or Subscription.objects.filter(user=user).exists()
    )


def login_subscription_state(user):
    """What a sign-in response should say about this account's plan.

    Returned by every sign-in path -- password, phone OTP, subscription OTP
    and SuperApp auto-login -- so the client has one flag to branch on instead
    of four differently-shaped answers. ``requires_subscription`` is False for
    a subscriber, and the extra keys are absent, so an active customer's
    response is unchanged apart from that one boolean.
    """
    if has_active_subscription(user):
        return {'requires_subscription': False}

    lapsed = has_ever_subscribed(user)
    instruction = resubscribe_instruction()
    message = (
        f'Your subscription has ended. {instruction}'
        if lapsed
        else f'An active FlipStar plan is required. {instruction}'
    )
    return {
        'requires_subscription': True,
        'subscription_code': LOGIN_REQUIRES_SUBSCRIPTION_CODE,
        'subscription_message': message,
        'previously_subscribed': lapsed,
    }


#: Refusing a coin purchase for want of access. Distinct from
#: SUBSCRIPTION_REQUIRED_CODE so a client can tell "you cannot post" from
#: "you cannot buy coins" and send the customer to the right place.
COIN_PURCHASE_REQUIRES_ACCESS_CODE = 'ACCESS_REQUIRED_FOR_COIN_PURCHASE'

COIN_PURCHASE_REQUIRES_ACCESS_MESSAGE = (
    'Coins can only be bought with an active FlipStar plan. '
    'Please subscribe or renew your plan, then try again.'
)


def coin_purchase_refusal(user):
    """Why this customer may not buy coins, or None if they may.

    One rule for every way in -- the USSD push, the SuperApp H5 order and the
    airtime charge -- because a check on only some of them is not a rule, it
    is a suggestion. The frontend hides the button; this is what makes it
    true when somebody calls the API directly.

    "Active access" is `has_active_subscription`, the same predicate that
    gates posting, so access cannot come to mean two different things
    depending on which feature asks. It already treats an `end_date` in the
    past as inactive however the status column reads, which is what makes an
    expired plan a refusal rather than a pass.

    Returns a ready-to-send body, or None. Deliberately not a boolean: the
    caller should not be composing its own wording for a rule defined here.
    """
    if has_active_subscription(user):
        return None
    return {
        'success': False,
        'code': COIN_PURCHASE_REQUIRES_ACCESS_CODE,
        'error': COIN_PURCHASE_REQUIRES_ACCESS_MESSAGE,
        'message': COIN_PURCHASE_REQUIRES_ACCESS_MESSAGE,
    }


ALREADY_SUBSCRIBED_CODE = 'ALREADY_SUBSCRIBED'


def active_subscription_for(user=None, phone_number=None, payment_method=None):
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
    if payment_method:
        qs = qs.filter(payment_method=payment_method)

    # An `end_date` in the past is not an active subscription however the
    # status column reads -- renewals that failed can leave the two disagreeing.
    qs = qs.filter(models.Q(end_date__isnull=True) | models.Q(end_date__gt=now))

    if user is not None and getattr(user, 'is_authenticated', False):
        return qs.filter(user=user).order_by('-start_date').first()

    if phone_number:
        from api.models import UserProfile
        from common.validators import lookup_variants

        phone_values = lookup_variants(phone_number)
        profile = UserProfile.objects.filter(phone_number__in=phone_values).first()
        if profile:
            return qs.filter(user=profile.user).order_by('-start_date').first()

        return (
            qs.filter(
                models.Q(telebirr_phone_number__in=phone_values)
                | models.Q(onevas_phone_number__in=phone_values)
            )
            .order_by('-start_date')
            .first()
        )

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


PAYMENT_PENDING_CODE = 'PAYMENT_PENDING'

#: How long after a USSD push a repeat attempt is treated as a double-tap
#: rather than a fresh purchase. Long enough to cover a confirmation that is
#: merely slow; short enough that a confirmation which never arrives does not
#: lock the caller out of subscribing for good.
PENDING_PAYMENT_WINDOW_SECONDS = 10 * 60


def pending_subscription_payment(user=None, phone_number=None, within_seconds=None):
    """A USSD subscription payment already awaiting confirmation, or None.

    Guards the gap the ``ALREADY_SUBSCRIBED`` check cannot see. That one keys
    on an *active* subscription, but a payment whose callback has not landed
    leaves the subscription *pending* -- so the caller looks like a
    non-subscriber, taps again, and is charged again. That is not hypothetical:
    when the telebirr callback has nowhere to land, every one of these stays
    pending indefinitely.
    """
    from api.models.subscription import SubscriptionPayment

    window = PENDING_PAYMENT_WINDOW_SECONDS if within_seconds is None else within_seconds
    since = timezone.now() - timedelta(seconds=window)

    qs = SubscriptionPayment.objects.filter(status='pending', created_at__gte=since)

    if user is not None and getattr(user, 'is_authenticated', False):
        found = qs.filter(user=user).order_by('-created_at').first()
        if found:
            return found

    if phone_number:
        # Unauthenticated initiates record the phone here, since there is no
        # account to attach the payment to yet.
        return qs.filter(metadata__phone_number=phone_number).order_by('-created_at').first()

    return None


def payment_pending_payload(message=None):
    """The refusal returned when a previous payment is still confirming."""
    return {
        'success': False,
        'code': PAYMENT_PENDING_CODE,
        'error': message
        or (
            'Your previous payment is still being confirmed. '
            'Please wait a moment before trying again.'
        ),
    }
