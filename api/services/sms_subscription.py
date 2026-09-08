"""
The SMS subscription lifecycle, shared by the aggregators.

Why this exists
---------------
A subscriber texts a keyword to the short code, the aggregator charges them and
then tells us. What has to happen next is identical whichever aggregator
delivered the news -- OneVAS or TIMWE -- because it is our side of the same
business arrangement: activate or renew the plan, record the payment, write
history, and text the subscriber the OTP that lets them actually reach the
service they just paid for.

The TIMWE endpoint previously did about half of that. It created a plan and
wrote history, but sent no SMS, recorded no payment, granted no free trial day,
and answered a repeat charge with "already active" instead of renewing. A
subscriber who texted the short code was billed and then received nothing --
no link, no OTP, no way in.

This module is that logic in one place, so the two channels cannot drift.

Relationship to the OneVAS webhook
----------------------------------
The semantics here are taken from ``OnevasWebhookView`` in
``api/views/subscription.py``, deliberately and to the letter -- the free-trial
rule, the cancel-other-durations rule, the renew-in-place rule, and the message
text. That view still contains its own inline copy and is not changed here: it
is live and carries real payments. This is where it should move when it is next
touched, and until then the two must be changed together.
"""

import uuid

from django.db import transaction
from django.utils import timezone

from api.models import (
    SubscriptionHistory,
    SubscriptionPayment,
    SubscriptionPlan,
    UserProfile,
)

#: What a subscriber texts to cancel, per plan. Quoted in the welcome SMS, so
#: it has to match what the aggregator is configured to recognise.
STOP_KEYWORDS = {
    'daily': 'STOP1',
    'weekly': 'STOP2',
    'monthly': 'STOP3',
    'ondemand': 'STOP',
}

#: How the price reads in the SMS: "5 ETB per day".
PRICE_PERIODS = {
    'daily': 'day',
    'weekly': 'week',
    'monthly': 'month',
    'ondemand': 'use',
}

#: Which STOP keyword cancels which plan. 'STOP' with no digit cancels
#: everything, matching the OneVAS handler.
STOP_KEYWORD_DURATIONS = {
    'STOP': 'daily',
    'STOP1': 'daily',
    'STOP2': 'weekly',
    'STOP3': 'monthly',
}

#: Granted once, to a phone number that has never subscribed before.
FIRST_TIME_FREE_TRIAL_DAYS = 1


class SubscribeResult:
    """What happened, and what the caller needs to send an SMS about it."""

    def __init__(self, *, action, plan, otp, free_trial_days, existing_user):
        #: 'created' or 'renewed'.
        self.action = action
        self.plan = plan
        self.otp = otp
        self.free_trial_days = free_trial_days
        self.existing_user = existing_user


def resolve_subscriber(phone_number):
    """The account behind an MSISDN, or None.

    Two lookups, because a subscriber may pay before they ever register: by
    profile phone number, then by a plan already carrying the number. The
    second also backfills the profile, so the link survives.
    """
    if not phone_number:
        return None

    profile = UserProfile.objects.filter(phone_number=phone_number).select_related('user').first()
    if profile is not None:
        return profile.user

    plan = (
        SubscriptionPlan.objects.filter(onevas_phone_number=phone_number)
        .select_related('user')
        .first()
    )
    if plan is None or plan.user is None:
        return None

    # Backfill, as the OneVAS handler does, so the next lookup is direct.
    if not plan.user.profile.phone_number:
        plan.user.profile.phone_number = phone_number
        plan.user.profile.save(update_fields=['phone_number'])
    return plan.user


def _generate_otp():
    from api.services.otp import OTPService

    return OTPService.generate_otp()


def _cancel_conflicting_plans(*, user, phone_number, duration_type, reason, metadata):
    """Cancel active plans of a *different* duration for this subscriber.

    One subscriber, one plan. Without this a subscriber who moves from daily to
    weekly holds both, and is billed for both.
    """
    conflicting = SubscriptionPlan.objects.filter(status='active')
    if user is not None:
        conflicting = conflicting.filter(user=user)
    else:
        conflicting = conflicting.filter(onevas_phone_number=phone_number, user__isnull=True)
    conflicting = conflicting.exclude(duration_type=duration_type)

    for plan in conflicting:
        plan.cancel(reason=reason)
        SubscriptionHistory.objects.create(
            user=plan.user,
            subscription=plan,
            tier=plan.tier,
            action='cancelled',
            reason=reason,
            metadata={**metadata, 'new_duration_type': duration_type},
        )


def _record_payment(plan, tier, payment_method):
    SubscriptionPayment.objects.create(
        subscription=plan,
        user=plan.user,
        amount=tier.price_etb,
        payment_method=payment_method,
        duration_type=tier.duration_type,
        period_start=plan.start_date,
        period_end=plan.end_date
        or timezone.now() + timezone.timedelta(days=tier.duration_days or 30),
        status='completed',
    )


@transaction.atomic
def subscribe(*, phone_number, tier, payment_method, metadata=None, user=None):
    """Activate or renew the subscription an aggregator has just charged for.

    Returns a :class:`SubscribeResult`. The caller sends the SMS, because only
    it knows which channel to send it over.

    ``user`` may be passed by a caller that has already identified the
    subscriber -- it is used as given rather than looked up again, so the
    account attributed here cannot disagree with the one the caller recorded.
    Omit it and the number is resolved here.
    """
    metadata = metadata or {}
    if user is None:
        user = resolve_subscriber(phone_number)
    otp = _generate_otp()

    _cancel_conflicting_plans(
        user=user,
        phone_number=phone_number,
        duration_type=tier.duration_type,
        reason='Cancelled due to new subscription of different duration type',
        metadata=metadata,
    )

    # An active plan of the same duration is a renewal, not a duplicate. The
    # subscriber has been charged again and their period must be extended.
    existing = SubscriptionPlan.objects.filter(status='active', duration_type=tier.duration_type)
    if user is not None:
        existing = existing.filter(user=user)
    else:
        existing = existing.filter(onevas_phone_number=phone_number, user__isnull=True)
    existing = existing.first()

    if existing is not None:
        existing.tier = tier
        existing.duration_type = tier.duration_type
        existing.setup_otp = otp
        existing.save(update_fields=['tier', 'duration_type', 'setup_otp'])
        existing.activate()
        _record_payment(existing, tier, payment_method)
        SubscriptionHistory.objects.create(
            user=existing.user,
            subscription=existing,
            tier=tier,
            action='renewed',
            reason=f'Subscription renewed via {payment_method}',
            metadata=metadata,
        )
        return SubscribeResult(
            action='renewed',
            plan=existing,
            otp=otp,
            free_trial_days=existing.free_trial_days or 0,
            existing_user=user is not None,
        )

    # First subscription for this number gets a complimentary day. Judged on
    # the phone rather than the account, because the SMS channel has no account
    # -- and a subscriber must not earn a fresh trial by unsubscribing.
    has_history = SubscriptionPlan.objects.filter(onevas_phone_number=phone_number).exists()
    free_trial_days = 0 if has_history else FIRST_TIME_FREE_TRIAL_DAYS

    plan = SubscriptionPlan.objects.create(
        user=user,
        tier=tier,
        duration_type=tier.duration_type,
        # Reusing the onevas_* column deliberately rather than adding a
        # parallel column per aggregator: every existing subscription query
        # already keys off it.
        onevas_phone_number=phone_number,
        onevas_subscription_id=str(uuid.uuid4()),
        subscription_source='sms',
        payment_method=payment_method,
        setup_otp=otp,
        free_trial_days=free_trial_days,
        status='pending',
        metadata=metadata,
    )
    # activate() owns the date arithmetic -- duration_days + free_trial_days --
    # and grants the tier's bonus coins exactly once.
    plan.activate()

    _record_payment(plan, tier, payment_method)
    SubscriptionHistory.objects.create(
        user=user,
        subscription=plan,
        tier=tier,
        action='created',
        reason=f'Subscription created via {payment_method} SMS',
        metadata={**metadata, 'sms_subscription': True},
    )

    return SubscribeResult(
        action='created',
        plan=plan,
        otp=otp,
        free_trial_days=free_trial_days,
        existing_user=user is not None,
    )


@transaction.atomic
def unsubscribe(*, phone_number, duration_type=None, reason, metadata=None, user=None):
    """Cancel the subscriber's active plans. Returns those cancelled.

    An empty list is a valid answer: the aggregator is reporting something it
    has already done, and there may be nothing left to cancel.
    """
    metadata = metadata or {}
    if user is None:
        user = resolve_subscriber(phone_number)

    plans = SubscriptionPlan.objects.filter(status='active')
    if user is not None:
        plans = plans.filter(user=user)
    else:
        plans = plans.filter(onevas_phone_number=phone_number)
    if duration_type:
        plans = plans.filter(duration_type=duration_type)

    cancelled = list(plans)
    for plan in cancelled:
        plan.cancel(reason=reason)
        SubscriptionHistory.objects.create(
            user=plan.user,
            subscription=plan,
            tier=plan.tier,
            action='cancelled',
            reason=reason,
            metadata=metadata,
        )
    return cancelled


def build_welcome_message(*, tier, result, phone_number, base_url):
    """The SMS a subscriber gets after being charged.

    Same shape as the OneVAS message, because it is the same product and
    subscribers on both channels should read the same thing: what they bought,
    what it costs, how to get in, and how to stop.
    """
    stop_keyword = STOP_KEYWORDS.get(tier.duration_type, 'STOP')
    price_period = PRICE_PERIODS.get(tier.duration_type, 'day')

    if result.free_trial_days > 0:
        trial = (
            f'You have {result.free_trial_days} day(s) of complimentary free trial. '
            f'After your free trial concludes, the subscription price will be '
            f'{tier.price_etb} ETB per {price_period}.'
        )
    else:
        trial = f'The subscription price is {tier.price_etb} ETB per {price_period}.'

    existing = '&existing_user=true' if result.existing_user else ''
    started = result.plan.start_date.strftime('%Y-%m-%d %H:%M')

    return (
        f'Dear valued customer, you have successfully subscribed to the {tier.name} '
        f'Flipstar service, effective from {started}. {trial} '
        f'To access your premium service, please click on '
        f'{base_url}?subscription_tp=true&phone={phone_number}{existing} '
        f'and enter your OTP: {result.otp}. '
        f'To cancel your subscription at any time, please send {stop_keyword} '
        f'to {tier.short_code}.'
    )


def send_subscription_sms(phone_number, message, tier):
    """Send over the aggregator's SMS channel.

    Routed through the existing OneVAS sender rather than a second client:
    there is one SMS gateway, and it is already keyed per tier. Imported
    locally because that lives in a view module.
    """
    from api.views.subscription import OnevasWebhookView

    return OnevasWebhookView().send_sms(phone_number, message, tier.duration_type)
