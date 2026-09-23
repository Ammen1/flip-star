"""
Renewing a lapsed short-code subscription by charging TIMWE, from the backend.

A subscriber on the TIMWE short code holds a SubscriptionPlan whose end_date
eventually passes. When that happens -- and only while the renewal switches
are on -- the backend charges the subscriber's registered number once for the
next period through TIMWE chargeAmount, and renews the plan only after TIMWE
confirms the charge. The client never asks for this and supplies none of its
terms: who is charged, which number, how much and for how long all come from
the server's own records.

The rules that keep this from charging anyone twice
---------------------------------------------------
* One live attempt per renewal period. A period is the plan plus the end_date
  that ran out. Each attempt's idempotency key is derived from that and its
  attempt number and is unique in the database, and a partial unique
  constraint on (subscription, renewal_period_end) allows one pending,
  successful or ambiguous charge per period. However many requests arrive
  while a plan is lapsed, at most one charge that could take money reaches
  TIMWE.
* A pending or ambiguous attempt is never followed by another. After a timeout
  the subscriber may already have paid; the answer comes from reconciling the
  reference code with TIMWE (``manage.py timwe_charge_check --reconcile``),
  never from charging again to find out.
* A refused attempt -- TIMWE answered no, or never received it -- took
  nothing, so it is tried again TIMWE_RENEWAL_RETRY_MINUTES later (default an
  hour), for up to TIMWE_RENEWAL_WINDOW_DAYS after the period ran out. That is
  the subscriber with too little airtime being renewed once they top up.
  After the window the plan stays expired until they opt in again.
* The plan is renewed only after a confirmed success, in one database
  transaction with the claim that marks the charge fulfilled. If that fails
  after TIMWE has charged, the charge stays success-but-unfulfilled: the next
  check applies it without charging again, and the reconciliation report lists
  it until then.

Who asks
--------
Nobody has to be using the app. An hourly beat job (``sweep_due_renewals``)
queues every lapsed airtime subscriber who is due, and the status endpoint and
posting a video ask for the one user in front of them. All three end in
``check_and_renew_subscription``, which applies every rule above.

What this cannot protect against
--------------------------------
TIMWE may renew short-code subscriptions itself. If it does, a charge from
here is a second charge for the same period. That is why
TIMWE_SUBSCRIPTION_RENEWAL_ENABLED exists and defaults off: turn it on only
once TIMWE has confirmed that renewals on this service are ours to charge.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from api.models.subscription import SubscriptionHistory, SubscriptionPayment, SubscriptionPlan
from api.models.timwe import TimweChargeTransaction
from api.services.subscription_access import has_active_subscription
from api.services.subscription_tiers import charging_service_id
from common.validators.phone import normalize_ethiopian_phone

logger = logging.getLogger(__name__)

RENEWAL_PURPOSE = TimweChargeTransaction.PURPOSE_SUBSCRIPTION_RENEWAL

# Where a subscriber stands. Values are stable: the status endpoint reports
# them and log searches key on them.
ACTIVE = 'active'  # an active subscription; nothing to do
RENEWED = 'renewed'  # this call charged and renewed
PAYMENT_PENDING = 'payment_pending'  # a renewal charge is in flight, ambiguous, or unapplied
EXPIRED = 'expired'  # a lapsed short-code subscriber not (yet) renewed
INACTIVE = 'inactive'  # no short-code subscription to renew

# Why, for EXPIRED and PAYMENT_PENDING.
REASON_DUE = 'renewal_due'
REASON_DISABLED = 'renewal_disabled'
REASON_FAILED = 'renewal_failed'
REASON_AWAITING = 'awaiting_confirmation'
REASON_UNAPPLIED = 'charged_not_yet_applied'
REASON_NO_MSISDN = 'no_registered_msisdn'
REASON_MSISDN_MISMATCH = 'msisdn_mismatch'
REASON_NOT_ATTEMPTED = 'not_attempted'

#: Plan statuses a lapsed short-code subscription can carry. Nothing marks a
#: plan 'expired' when its period ends -- it stays 'active' with an end_date in
#: the past -- but a plan in either of the others is lapsed too. 'cancelled'
#: is absent on purpose: that subscriber unsubscribed and must never be
#: charged again.
RENEWABLE_STATUSES = ('active', 'expired', 'grace_period')

#: How long a queued renewal suppresses queueing another for the same period.
#: The task is idempotent regardless; this only saves a queue round trip for
#: every poll of the status endpoint while one is waiting to run.
QUEUE_MARKER_SECONDS = 120

#: A refused charge may be followed by another after this share of the retry
#: interval. A little under the whole of it, because the hourly sweep starts
#: on the hour and the attempt it is following may have run a few seconds
#: past one; waiting the full hour would skip every other hour.
RETRY_EARLY = 0.9

#: Retries are never closer together than this, whatever is configured.
MIN_RETRY_MINUTES = 10

#: The most subscribers one sweep queues. Any beyond are next in line an hour
#: later, when the ones queued now have an attempt on record.
SWEEP_BATCH = 500


@dataclass(frozen=True)
class RenewalStatus:
    state: str
    plan: SubscriptionPlan | None = None
    charge: TimweChargeTransaction | None = None
    reason: str = ''

    @property
    def has_subscription(self) -> bool:
        return self.state in (ACTIVE, RENEWED)


def renewal_enabled() -> bool:
    """Both switches: the master one, and this flow's own."""
    return bool(getattr(settings, 'TIMWE_CHARGING_ENABLED', False)) and bool(
        getattr(settings, 'TIMWE_SUBSCRIPTION_RENEWAL_ENABLED', False)
    )


def _short_code() -> str:
    return getattr(settings, 'SMS_SHORT_CODE', '') or '9286'


def _mask(msisdn: str) -> str:
    digits = msisdn or ''
    return f'{digits[:5]}****{digits[-3:]}' if len(digits) > 6 else digits


def _setting_int(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def retry_interval() -> timedelta:
    """How long after TIMWE refuses a renewal charge the next attempt is made."""
    minutes = _setting_int('TIMWE_RENEWAL_RETRY_MINUTES', 60)
    return timedelta(minutes=max(minutes, MIN_RETRY_MINUTES))


def renewal_window() -> timedelta:
    """How long after a period runs out renewal keeps being attempted."""
    return timedelta(days=max(_setting_int('TIMWE_RENEWAL_WINDOW_DAYS', 7), 1))


def _renewable_plans(now):
    """Every TIMWE short-code plan whose period ran out inside the renewal window.

    Identified by what the subscription actually is -- a TIMWE SMS plan on the
    configured short code, for a tier with a price and a duration -- never by
    anything the client says. OneVAS and telebirr plans are never candidates:
    those subscribers agreed to be billed somewhere else.
    """
    return SubscriptionPlan.objects.filter(
        payment_method='timwe',
        subscription_source='sms',
        status__in=RENEWABLE_STATUSES,
        end_date__isnull=False,
        end_date__lte=now,
        end_date__gte=now - renewal_window(),
        tier__short_code=_short_code(),
        tier__duration_days__gt=0,
        tier__price_etb__gt=0,
    ).select_related('tier')


def _for_this_service(plan) -> bool:
    """A plan TIMWE recorded against another service is not this service's to renew."""
    service_id = getattr(settings, 'TIMWE_SERVICE_ID', '') or ''
    plan_service = (plan.metadata or {}).get('service_id') or ''
    return not (service_id and plan_service and plan_service != service_id)


def lapsed_short_code_plan(user):
    """The user's TIMWE short-code subscription whose period has run out, or None.

    The newest one, and only inside the renewal window: a subscription that
    ran out longer ago than TIMWE_RENEWAL_WINDOW_DAYS is not renewed from here.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return None

    for plan in _renewable_plans(timezone.now()).filter(user=user).order_by('-end_date'):
        if _for_this_service(plan):
            return plan
    return None


def renewal_idempotency_key(plan, attempt: int = 1) -> str:
    """One key per (plan, period that ran out, attempt) -- each charged at most once.

    The first attempt keeps the key it has always had; a retry after a refusal
    adds its number.
    """
    key = f'sub-renewal:{plan.pk}:{plan.end_date.isoformat()}'
    return key if attempt <= 1 else f'{key}:{attempt}'


def _period_charges(plan):
    return TimweChargeTransaction.objects.filter(
        purpose=RENEWAL_PURPOSE, subscription=plan, renewal_period_end=plan.end_date
    )


def existing_renewal_charge(plan):
    """The latest charge made for this plan's lapsed period, if any."""
    return _period_charges(plan).order_by('-created_at').first()


def next_attempt(plan) -> int:
    """The number the next charge for this plan's lapsed period would carry.

    Counted, not stored: two workers that count the same number build the same
    idempotency key, and the second finds the first's charge instead of
    sending one.
    """
    return _period_charges(plan).count() + 1


def _may_try_again(charge, now) -> bool:
    """TIMWE refused this charge, so nothing was taken, and it is time to try again.

    Only ever a refusal: 'failed' is recorded solely for a Fault from the MA or
    a request that never reached it. A pending, ambiguous or successful charge
    is never followed by another.
    """
    return charge.status == 'failed' and now >= charge.created_at + retry_interval() * RETRY_EARLY


def _charge_number(user, plan):
    """``(number, '')`` for the number a renewal may charge, or ``(number, reason)`` not to.

    The number charged is the account's own registered number -- and it must
    be the number TIMWE subscribed on the short code. Charging any other would
    bill someone who never opted in.
    """
    registered = normalize_ethiopian_phone(
        getattr(getattr(user, 'profile', None), 'phone_number', '') or ''
    )
    if not registered:
        return '', REASON_NO_MSISDN
    subscribed = normalize_ethiopian_phone(plan.onevas_phone_number or '')
    if subscribed and subscribed != registered:
        return registered, REASON_MSISDN_MISMATCH
    return registered, ''


def _status_from_charge(plan, charge) -> RenewalStatus:
    if charge.status == 'success':
        # Charged. Were it applied the plan would be active again, so it is not.
        return RenewalStatus(PAYMENT_PENDING, plan, charge, REASON_UNAPPLIED)
    if charge.is_ambiguous:
        return RenewalStatus(PAYMENT_PENDING, plan, charge, REASON_AWAITING)
    return RenewalStatus(EXPIRED, plan, charge, REASON_FAILED)


def subscription_status(user) -> RenewalStatus:
    """Where the user stands, without charging anything. Safe on any request."""
    if has_active_subscription(user):
        return RenewalStatus(ACTIVE)

    plan = lapsed_short_code_plan(user)
    if plan is None:
        return RenewalStatus(INACTIVE)

    charge = existing_renewal_charge(plan)
    if charge is not None and not _may_try_again(charge, timezone.now()):
        return _status_from_charge(plan, charge)
    return RenewalStatus(
        EXPIRED, plan, charge, reason=REASON_DUE if renewal_enabled() else REASON_DISABLED
    )


def check_and_renew_subscription(user) -> RenewalStatus:
    """Check the user's subscription and renew a lapsed short-code one, once.

    Synchronous: when a charge is due, this waits for TIMWE (up to
    TIMWE_CHARGE_TIMEOUT). Request paths that must not wait call
    ``schedule_renewal`` instead and read ``subscription_status``.
    """
    status = subscription_status(user)

    charge = status.charge
    if charge is not None and charge.status == 'success' and charge.fulfilled_at is None:
        # TIMWE has already taken the money. Finish the renewal; never charge again.
        apply_renewal(charge)
        return _after_apply(user, status.plan, charge)

    if status.state != EXPIRED or status.reason != REASON_DUE:
        return status
    return _renew(user, status.plan)


def _after_apply(user, plan, charge) -> RenewalStatus:
    plan.refresh_from_db()
    if plan.is_active:
        return RenewalStatus(RENEWED, plan, charge)
    return subscription_status(user)


def _renew(user, plan) -> RenewalStatus:
    from api.integrations.timwe.errors import TimweConfigurationError
    from api.services.timwe_charging import ChargeRefused, request_charge

    tier = plan.tier
    attempt = next_attempt(plan)
    base_log = {
        'operation': 'subscription_renewal',
        'user_id': user.pk,
        'plan_id': str(plan.pk),
        'period_end': plan.end_date.isoformat(),
        'attempt': attempt,
    }

    registered, skip = _charge_number(user, plan)
    if skip:
        extra = {**base_log, 'reason': skip}
        if registered:
            extra['masked_msisdn'] = _mask(registered)
        logger.warning('SUBSCRIPTION_RENEWAL_SKIPPED', extra=extra)
        return RenewalStatus(EXPIRED, plan, reason=skip)

    logger.info(
        'SUBSCRIPTION_RENEWAL_STARTED',
        extra={
            **base_log,
            'amount': int(tier.price_etb),
            'tier': tier.name,
            'masked_msisdn': _mask(registered),
        },
    )
    try:
        result = request_charge(
            user=user,
            msisdn=registered,
            # From the tier -- never from the request.
            amount=tier.price_etb,
            description=f'FlipStar {tier.name} renewal',
            idempotency_key=renewal_idempotency_key(plan, attempt),
            subscription_tier=tier,
            purpose=RENEWAL_PURPOSE,
            subscription=plan,
            renewal_period_end=plan.end_date,
            short_code=tier.short_code or '',
            product_id=tier.product_id or '',
            # The service this plan's product is provisioned under. Empty
            # falls back to the deployment default, so a tier with nothing
            # set behaves exactly as it did before.
            service_id=charging_service_id(tier),
        )
    except (ChargeRefused, TimweConfigurationError) as exc:
        # Refused before anything was sent -- unless a concurrent attempt owns
        # this period and only the replay was refused. Report that one. An
        # earlier refusal owns nothing; this attempt was simply not made.
        existing = existing_renewal_charge(plan)
        if existing is not None and existing.status != 'failed':
            return _status_from_charge(plan, existing)
        logger.warning(
            'SUBSCRIPTION_RENEWAL_NOT_ATTEMPTED',
            extra={**base_log, 'reason': type(exc).__name__},
        )
        return RenewalStatus(EXPIRED, plan, reason=REASON_NOT_ATTEMPTED)

    charge = result.transaction
    charge_log = {**base_log, 'reference_code': charge.reference_code, 'charge_id': str(charge.pk)}
    if not result.created:
        logger.info('SUBSCRIPTION_RENEWAL_DUPLICATE_PREVENTED', extra=charge_log)

    if result.succeeded:
        apply_renewal(charge)
        return _after_apply(user, plan, charge)

    status = _status_from_charge(plan, charge)
    event = (
        'SUBSCRIPTION_RENEWAL_AMBIGUOUS'
        if status.state == PAYMENT_PENDING
        else 'SUBSCRIPTION_RENEWAL_FAILED'
    )
    logger.warning(
        event, extra={**charge_log, 'status': charge.status, 'timwe_error_code': charge.error_code}
    )
    return status


def apply_renewal(charge) -> bool:
    """Renew the plan a confirmed charge paid for, exactly once.

    The claim on ``fulfilled_at`` and every write it pays for commit together:
    if anything fails the claim rolls back with it, the charge stays
    success-but-unfulfilled, and the next call tries again -- without charging.
    Returns True when this call applied the renewal.
    """
    if charge.purpose != RENEWAL_PURPOSE or charge.subscription_id is None:
        raise ValueError('This charge did not pay for a subscription renewal.')

    now = timezone.now()
    try:
        with transaction.atomic():
            claimed = TimweChargeTransaction.objects.filter(
                pk=charge.pk, status='success', fulfilled_at__isnull=True
            ).update(fulfilled_at=now)
            if not claimed:
                return False

            plan = (
                SubscriptionPlan.objects.select_for_update()
                .select_related('tier')
                .get(pk=charge.subscription_id)
            )
            tier = plan.tier

            # A period that ran out starts again now: new_end = now + duration.
            # The free-trial days are not added again -- they were a one-off.
            # If the plan is somehow already running (renewed through another
            # path while this charge was in flight) the subscriber has paid for
            # this period too, so it is added on rather than lost.
            starts = plan.end_date if plan.end_date and plan.end_date > now else now
            if starts > now:
                logger.warning(
                    'SUBSCRIPTION_RENEWAL_ON_RUNNING_PLAN',
                    extra={'reference_code': charge.reference_code, 'plan_id': str(plan.pk)},
                )
            plan.status = 'active'
            plan.start_date = now
            plan.end_date = starts + timedelta(days=tier.duration_days)
            plan.next_renewal_date = plan.end_date
            plan.grace_started_at = None
            plan.grace_expires_at = None
            plan.save(
                update_fields=[
                    'status',
                    'start_date',
                    'end_date',
                    'next_renewal_date',
                    'grace_started_at',
                    'grace_expires_at',
                    'updated_at',
                ]
            )

            SubscriptionPayment.objects.create(
                subscription=plan,
                user=plan.user,
                # The provider transaction column; the MA reference goes here
                # so the payment traces back to exactly one TIMWE charge.
                onevas_transaction_id=charge.reference_code,
                amount=charge.amount,
                currency=charge.currency,
                status='completed',
                payment_method='timwe',
                duration_type=plan.duration_type,
                period_start=now,
                period_end=plan.end_date,
                metadata={
                    'source': 'timwe_charge_amount',
                    'charge_id': str(charge.pk),
                    'reference_code': charge.reference_code,
                },
            )
            SubscriptionHistory.objects.create(
                user=plan.user,
                subscription=plan,
                tier=tier,
                action='renewed',
                reason='Renewed by the backend through TIMWE chargeAmount',
                metadata={
                    'reference_code': charge.reference_code,
                    'charge_id': str(charge.pk),
                    'previous_end_date': (
                        charge.renewal_period_end.isoformat() if charge.renewal_period_end else None
                    ),
                },
            )
    except Exception:
        logger.exception(
            'SUBSCRIPTION_RENEWAL_APPLY_FAILED',
            extra={'reference_code': charge.reference_code, 'charge_id': str(charge.pk)},
        )
        return False

    # The subscriber has just been charged by us rather than by the MA, so the
    # MA sends them nothing. Outside the transaction above: a text that cannot
    # be queued must not undo a renewal that has been paid for.
    try:
        from api.services import sms_subscription

        sms_subscription.send_subscription_sms(
            charge.msisdn,
            # The link, so every charge tells the subscriber how to get in.
            # No OTP: this path leaves plan.setup_otp alone, so whatever code
            # they hold still works and a new one would break it.
            sms_subscription.build_renewal_message(
                tier=tier,
                plan=plan,
                phone_number=charge.msisdn,
                base_url=settings.TIMWE_SUBSCRIPTION_LINK_BASE,
            ),
            tier,
            purpose='subscription_renewal',
            # One message per charge, however many times this is retried.
            idempotency_key=f'renewal-sms:{charge.reference_code}',
        )
    except Exception:
        logger.exception(
            'SUBSCRIPTION_RENEWAL_SMS_FAILED',
            extra={'reference_code': charge.reference_code},
        )

    logger.info(
        'SUBSCRIPTION_RENEWAL_APPLIED',
        extra={
            'operation': 'subscription_renewal',
            'reference_code': charge.reference_code,
            'plan_id': str(charge.subscription_id),
            'new_end_date': plan.end_date.isoformat(),
        },
    )
    return True


def schedule_renewal(user, plan) -> bool:
    """Queue the renewal off the request path. Returns False if it could not be queued.

    Idempotent end to end -- the task charges at most once per period whatever
    happens -- so the cache marker only saves a queue round trip per poll.
    """
    from django.core.cache import cache

    from api.tasks.subscription_renewal import renew_expired_subscription

    marker = f'timwe-renewal-queued:{plan.pk}:{plan.end_date.timestamp():.6f}'
    try:
        if not cache.add(marker, 1, timeout=QUEUE_MARKER_SECONDS):
            return True
    except Exception:
        # No cache is no reason not to queue; the task is idempotent anyway.
        logger.warning('SUBSCRIPTION_RENEWAL_MARKER_UNAVAILABLE', extra={'plan_id': str(plan.pk)})

    try:
        renew_expired_subscription.delay(user.pk)
    except Exception:
        try:
            cache.delete(marker)
        except Exception:  # noqa: S110 - already failing; the next poll retries
            pass
        logger.exception('SUBSCRIPTION_RENEWAL_NOT_QUEUED', extra={'plan_id': str(plan.pk)})
        return False

    logger.info(
        'SUBSCRIPTION_RENEWAL_QUEUED',
        extra={'operation': 'subscription_renewal', 'user_id': user.pk, 'plan_id': str(plan.pk)},
    )
    return True


# ---------------------------------------------------------------------------
# The hourly sweep
# ---------------------------------------------------------------------------


def _charging_not_working():
    """An outcome that says charging itself is not working -- our credentials,
    configuration or address, the network, or an MA that takes the request and
    never answers -- rather than anything about the subscriber."""
    from api.integrations.timwe.charge import OUTCOME_REJECTED, OUTCOME_UNREACHABLE
    from api.integrations.timwe.errors import CHARGE_PERMANENT

    refused_for_our_reasons = Q(status='failed') & (
        Q(outcome=OUTCOME_UNREACHABLE)
        | Q(error_code__in=CHARGE_PERMANENT)
        | Q(outcome=OUTCOME_REJECTED, error_code='')
    )
    return refused_for_our_reasons | Q(status__in=('timeout', 'unknown'))


def charging_looks_broken(now) -> bool:
    """Renewal charges finished lately, and not one of them worked.

    While that holds, the sweep sends one charge an hour rather than hundreds
    that would all end the same way: refused, which looks like an attack to
    TIMWE, or unanswered, which leaves hundreds of ambiguous charges to
    reconcile by hand. The first that succeeds, or is refused for a reason of
    the subscriber's, ends it. A subscriber short of airtime is not a fault:
    those are what the retries are for.
    """
    recent = TimweChargeTransaction.objects.filter(
        purpose=RENEWAL_PURPOSE, completed_at__gte=now - retry_interval()
    )
    broken = _charging_not_working()
    return recent.filter(broken).exists() and not recent.exclude(broken).exists()


def _sweep_candidates(now):
    """Lapsed plans the sweep may queue: inside the window, with no live charge
    for the period, no refusal too recent to follow, and no other subscription
    active. Newest first, so a backlog clears from the most recent lapses."""
    from api.models import Subscription

    holding = TimweChargeTransaction.objects.filter(
        purpose=RENEWAL_PURPOSE,
        subscription=OuterRef('pk'),
        renewal_period_end=OuterRef('end_date'),
    ).filter(
        Q(status__in=('pending', 'timeout', 'unknown'))
        | Q(created_at__gt=now - retry_interval() * RETRY_EARLY)
    )
    active_plan = SubscriptionPlan.objects.filter(
        user=OuterRef('user'), status='active', end_date__gt=now
    )
    active_legacy = Subscription.objects.filter(user=OuterRef('user'), expires_at__gt=now)
    return (
        _renewable_plans(now)
        .filter(user__isnull=False)
        .filter(~Exists(holding), ~Exists(active_plan), ~Exists(active_legacy))
        .select_related('tier', 'user__profile')
        .order_by('-end_date')
    )


def due_renewals(now=None):
    """Yield ``(plan, skip_reason)`` for each subscriber the sweep would act on.

    One plan per user -- their newest for this service, which is the one
    renewal charges for. ``skip_reason`` is empty when the plan is due a
    charge. Reads only; ``timwe_charge_check --renewals`` prints it.
    """
    now = now or timezone.now()
    seen = set()
    for plan in _sweep_candidates(now).iterator(chunk_size=500):
        if plan.user_id in seen or not _for_this_service(plan):
            continue
        seen.add(plan.user_id)
        _, skip = _charge_number(plan.user, plan)
        yield plan, skip


def sweep_due_renewals(limit: int = SWEEP_BATCH) -> dict:
    """Queue a renewal for every lapsed airtime subscription that is due one.

    Run hourly by celery beat, so a subscriber is renewed whether or not they
    open the app. Charges nothing itself: each subscriber's renewal is its own
    task, through check_and_renew_subscription, which decides again with every
    guard. A subscriber queued here and by the app in the same minute is still
    charged at most once.
    """
    from api.integrations.timwe.charge import TimweChargeService
    from api.integrations.timwe.errors import TimweConfigurationError

    summary = {'queued': 0, 'skipped': 0, 'canary': False, 'ran': False}
    if not renewal_enabled():
        return summary
    try:
        TimweChargeService.ensure_configured()
    except TimweConfigurationError as exc:
        # Names only: the message never carries a value.
        logger.error(
            'SUBSCRIPTION_RENEWAL_SWEEP_NOT_CONFIGURED',
            extra={'operation': 'subscription_renewal', 'reason': str(exc)},
        )
        return summary

    summary['ran'] = True
    now = timezone.now()
    if charging_looks_broken(now):
        limit = 1
        summary['canary'] = True
        logger.warning(
            'SUBSCRIPTION_RENEWAL_SWEEP_CANARY',
            extra={
                'operation': 'subscription_renewal',
                'reason': 'no recent renewal charge worked; sending one',
            },
        )

    for plan, skip in due_renewals(now):
        if summary['queued'] >= limit:
            break
        if skip:
            summary['skipped'] += 1
            continue
        if not schedule_renewal(plan.user, plan):
            # The broker is not taking tasks; the rest would fail the same way.
            break
        summary['queued'] += 1

    logger.info(
        'SUBSCRIPTION_RENEWAL_SWEEP', extra={'operation': 'subscription_renewal', **summary}
    )
    return summary
