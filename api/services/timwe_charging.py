"""
Charging a subscriber's airtime through TIMWE, as a recorded transaction.

This is the only thing that should call TimweChargeService.execute(). The
client speaks the protocol; this module owns everything that makes it safe to
point at real money:

    validate input  ->  record the charge as PENDING (committed)
                    ->  call the MA                (outside any DB transaction)
                    ->  record exactly one outcome
                    ->  fulfil, exactly once, only on success

Why the PENDING row is committed before the call
------------------------------------------------
If the process dies while the MA is thinking -- up to 60 seconds, per the
guide -- the committed row is the only evidence a charge may be in flight. A
retry with the same idempotency key finds it and does not charge again.
Writing the row *after* the call would leave a crash between the two with the
subscriber billed and nothing on our side to say so.

The rule for retries
--------------------
One transaction row is at most one call to the MA. Nothing in this module
ever re-executes a transaction.

A retry is therefore a *new* transaction with a *new* idempotency key, and the
caller should start one only when the previous outcome proved nothing was
charged (``definitely_not_charged``). After a timeout or an unreadable reply
the subscriber may already have paid; the guide defines no status query for
chargeAmount, so the answer comes from reconciling ``reference_code`` against
TIMWE's own records -- never from charging again to find out.
"""

import logging
import uuid
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from api.integrations.timwe.charge import (
    OUTCOME_REJECTED,
    OUTCOME_SUCCESS,
    OUTCOME_TIMEOUT,
    OUTCOME_UNKNOWN,
    OUTCOME_UNREACHABLE,
    ChargeOutcome,
    TimweChargeService,
)
from api.integrations.timwe.errors import (
    CHARGE_AMOUNT_OUT_OF_RANGE,
    CHARGE_FAILED,
    TimweChargingDisabled,
    TimweError,
)
from api.models.timwe import TimweChargeTransaction
from api.services.concurrency import claim_transition

logger = logging.getLogger(__name__)

#: Outcome -> the model's coarser status.
STATUS_FOR_OUTCOME = {
    OUTCOME_SUCCESS: 'success',
    OUTCOME_REJECTED: 'failed',
    OUTCOME_UNREACHABLE: 'failed',
    OUTCOME_TIMEOUT: 'timeout',
    OUTCOME_UNKNOWN: 'unknown',
}

#: Prefix on every reference we generate, so our charges are recognisable in
#: TIMWE's reports. Two characters plus 28 hex digits fills the guide's
#: 30-character limit exactly (p.21).
REFERENCE_PREFIX = 'FS'


class ChargeRefused(TimweError):
    """The charge was not attempted: bad input, or a reused idempotency key."""


#: TIMWE_CHARGING_ENABLED is false, so nothing may be sent. A configuration
#: error, so callers that already hide configuration details from end users
#: (the coin purchase view answers 503) treat it the same way. Defined beside
#: the client, which enforces the switch too; re-exported here for callers.
ChargingDisabled = TimweChargingDisabled


def charging_enabled() -> bool:
    """The master switch. No chargeAmount leaves the process while it is off."""
    return TimweChargeService.charging_enabled()


@dataclass(frozen=True)
class ChargeResult:
    """What the caller needs to answer the user and decide what comes next."""

    transaction: TimweChargeTransaction
    #: False when an existing transaction was returned for a repeated key --
    #: in which case the MA was not called again.
    created: bool

    @property
    def status(self) -> str:
        return self.transaction.status

    @property
    def succeeded(self) -> bool:
        return self.transaction.status == 'success'

    @property
    def is_ambiguous(self) -> bool:
        return self.transaction.is_ambiguous

    @property
    def can_retry_with_new_key(self) -> bool:
        """Safe to start a fresh attempt: this one provably charged nothing."""
        return self.transaction.outcome in (OUTCOME_REJECTED, OUTCOME_UNREACHABLE) and bool(
            self.transaction.retryable
        )


def new_reference_code() -> str:
    """A fresh, unique MA reference: ``FS`` + 28 hex digits = 30 characters."""
    return f'{REFERENCE_PREFIX}{uuid.uuid4().hex[:28]}'


def _same_request(existing, *, msisdn, amount, currency) -> bool:
    return (
        existing.msisdn == msisdn
        and int(existing.amount) == int(amount)
        and existing.currency == currency
    )


def request_charge(
    *,
    user,
    msisdn,
    amount,
    description,
    idempotency_key,
    coin_package=None,
    subscription_tier=None,
    charge_code='',
    purpose='',
    subscription=None,
    renewal_period_end=None,
    short_code='',
    product_id='',
):
    """Charge a subscriber once, recording the attempt. Returns a ChargeResult.

    Raises ChargeRefused (or TimweConfigurationError, including
    ChargingDisabled) before anything is recorded or sent, for problems that
    are ours: the master switch off, missing configuration, an unusable
    number, an amount the MA cannot represent, a key reused for a different
    charge. Every MA or network failure is instead an outcome on the returned
    transaction.
    """
    if not charging_enabled():
        raise ChargingDisabled(
            'TIMWE charging is switched off (TIMWE_CHARGING_ENABLED is false). Nothing was sent.'
        )
    if not idempotency_key:
        raise ChargeRefused('An idempotency key is required for every charge.')

    # Validation first, so an invalid request never leaves a PENDING row that
    # looks like a charge in flight.
    TimweChargeService.ensure_configured()
    try:
        normalized = TimweChargeService.normalize_msisdn(msisdn)
        TimweChargeService.format_amount(amount)
        text = TimweChargeService.validate_description(description)
        currency = TimweChargeService.validate_currency()
    except TimweError as exc:
        raise ChargeRefused(str(exc)) from exc

    existing = TimweChargeTransaction.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return _replay(existing, msisdn=normalized, amount=amount, currency=currency)

    try:
        with transaction.atomic():
            charge = TimweChargeTransaction.objects.create(
                user=user,
                idempotency_key=idempotency_key,
                reference_code=new_reference_code(),
                msisdn=normalized,
                amount=int(amount),
                currency=currency,
                description=text,
                charge_code=charge_code or '',
                coin_package=coin_package,
                subscription_tier=subscription_tier,
                purpose=purpose or '',
                subscription=subscription,
                renewal_period_end=renewal_period_end,
                short_code=short_code or '',
                service_id=TimweChargeService.get_service_id(),
                product_id=product_id or '',
                status='pending',
            )
    except IntegrityError:
        # Lost a race with a concurrent request for the same charge -- the same
        # key, or for a renewal the same (subscription, period). Theirs is the
        # charge; this one must not become a second.
        try:
            existing = TimweChargeTransaction.objects.get(idempotency_key=idempotency_key)
        except TimweChargeTransaction.DoesNotExist:
            # The key is free, so the collision was the one-renewal-per-period
            # constraint: another attempt owns this subscription period.
            existing = (
                TimweChargeTransaction.objects.filter(
                    purpose=purpose,
                    subscription=subscription,
                    renewal_period_end=renewal_period_end,
                ).first()
                if subscription is not None
                else None
            )
            if existing is None:
                raise
        return _replay(existing, msisdn=normalized, amount=amount, currency=currency)

    logger.info(
        'TIMWE_CHARGE_REQUESTED',
        extra={
            'operation': 'timwe_charge',
            'reference_code': charge.reference_code,
            'service_id': TimweChargeService.get_service_id(),
            'amount': int(charge.amount),
            'currency': charge.currency,
            'masked_msisdn': charge.masked_msisdn,
        },
    )

    # Deliberately outside any database transaction: the MA may take a full
    # minute, and holding a transaction open that long pins a connection and
    # any locks it took.
    try:
        outcome = TimweChargeService.execute(
            msisdn=normalized,
            amount=amount,
            description=text,
            reference_code=charge.reference_code,
            charge_code=charge_code or '',
        )
    except TimweChargingDisabled:
        # The client refused before building a request -- the switch went off
        # between the check above and here. Nothing was sent.
        outcome = ChargeOutcome(
            OUTCOME_UNREACHABLE, message='Charging was switched off; nothing was sent.'
        )
    except Exception:
        # Something of ours failed after the row was committed. What happened
        # at the MA is unknown, so the row is closed as ambiguous rather than
        # left PENDING for ever or marked failed on no evidence.
        logger.exception(
            'TIMWE_CHARGE_CLIENT_ERROR',
            extra={'operation': 'timwe_charge', 'reference_code': charge.reference_code},
        )
        outcome = ChargeOutcome(OUTCOME_UNKNOWN, message='Internal error while charging.')

    _record(charge, outcome)
    charge.refresh_from_db()
    return ChargeResult(transaction=charge, created=True)


def _replay(existing, *, msisdn, amount, currency):
    """Return the charge already made for this key, without calling the MA."""
    if not _same_request(existing, msisdn=msisdn, amount=amount, currency=currency):
        # The same key naming a different charge is a client bug, and with
        # money the safe response to a bug is to refuse loudly -- quietly
        # returning the old result would tell the caller a charge it never
        # asked for had succeeded.
        raise ChargeRefused(
            'This idempotency key was already used for a different charge. '
            'Use a new key for a new purchase.'
        )
    logger.info(
        'TIMWE_CHARGE_REPLAYED',
        extra={
            'operation': 'timwe_charge',
            'reference_code': existing.reference_code,
            'status': existing.status,
        },
    )
    return ChargeResult(transaction=existing, created=False)


def _record(charge, outcome):
    """Write the outcome onto the PENDING row, exactly once."""
    status = STATUS_FOR_OUTCOME[outcome.outcome]

    if outcome.outcome == OUTCOME_UNREACHABLE:
        # Nothing was sent, so a new attempt cannot double-charge.
        retryable = True
    elif outcome.outcome == OUTCOME_REJECTED:
        # The MA answered; its code says whether another try could succeed.
        retryable = TimweChargeService.is_retryable(outcome.error_code)
    else:
        # Success needs no retry, and an ambiguous outcome must not get one.
        retryable = False

    claimed = claim_transition(
        TimweChargeTransaction,
        charge.pk,
        expect='pending',
        to=status,
        outcome=outcome.outcome,
        error_code=(outcome.error_code or '')[:16],
        error_message=(outcome.message or '')[:2000],
        retryable=retryable,
        http_status=outcome.http_status,
        duration_ms=outcome.duration_ms,
        completed_at=timezone.now(),
    )
    if not claimed:
        # Only the creator holds a PENDING row, so this means something else
        # already closed it. Its record stands.
        logger.warning(
            'TIMWE_CHARGE_ALREADY_RECORDED',
            extra={'operation': 'timwe_charge', 'reference_code': charge.reference_code},
        )
        return

    log = logger.info if outcome.success else logger.warning
    log(
        'TIMWE_CHARGE_COMPLETED',
        extra={
            'operation': 'timwe_charge',
            'reference_code': charge.reference_code,
            'service_id': TimweChargeService.get_service_id(),
            'amount': int(charge.amount),
            'currency': charge.currency,
            'masked_msisdn': charge.masked_msisdn,
            'result': outcome.outcome,
            'timwe_error_code': outcome.error_code or '',
            'http_status': outcome.http_status,
            'duration_ms': outcome.duration_ms,
        },
    )


# ---------------------------------------------------------------------------
# What a user is told
# ---------------------------------------------------------------------------


def user_message(result: ChargeResult) -> str:
    """A message safe to show the subscriber.

    Never the MA's own text -- that names internal services and echoes request
    fields -- and never anything that implies they may be charged twice.
    """
    charge = result.transaction
    if charge.status == 'success':
        return 'Payment successful.'
    if result.is_ambiguous:
        return (
            'We are confirming your payment with the network. You will not be '
            'charged twice -- please check your balance shortly.'
        )
    if charge.outcome == OUTCOME_UNREACHABLE:
        return 'Airtime payments are temporarily unavailable. You have not been charged.'
    if charge.error_code == CHARGE_AMOUNT_OUT_OF_RANGE:
        return 'This amount cannot be charged to your airtime.'
    if charge.error_code == CHARGE_FAILED:
        return (
            'The payment could not be completed. Please check your airtime balance and try again.'
        )
    # Authentication, service-configuration and input codes are our problem,
    # not the subscriber's, and are not described to them as their fault.
    return 'Airtime payments are temporarily unavailable. You have not been charged.'


# ---------------------------------------------------------------------------
# The business flow: buying coins with airtime
# ---------------------------------------------------------------------------


class AirtimePurchaseRefused(TimweError):
    """The purchase was refused before any charge was attempted."""


def purchase_coins_with_airtime(*, user, package, idempotency_key):
    """Charge the account's own number for a coin package, then credit it.

    The price comes from the CoinPackage row, never from the request -- the
    same rule the Telebirr purchase flows follow (api/services/coin_packages.py).
    The number charged is the account's own verified phone number, never one
    the client supplies: otherwise any user could bill someone else's airtime.

    Returns ``(ChargeResult, coin_transaction_or_None)``.
    """
    from common.validators.payment import AIRTIME, validate_pay_method

    if not package.is_active:
        raise AirtimePurchaseRefused('This coin package is not available.')

    # Airtime is permitted only at the one price common/validators/payment.py
    # allows. Raises a ValidationError for any other package.
    validate_pay_method(AIRTIME, package.price_etb)

    msisdn = getattr(getattr(user, 'profile', None), 'phone_number', '') or ''
    if not msisdn:
        raise AirtimePurchaseRefused(
            'Add and verify a phone number on your account to pay with airtime.'
        )

    result = request_charge(
        user=user,
        msisdn=msisdn,
        amount=package.price_etb,
        description=f'FlipStar {package.name}',
        idempotency_key=idempotency_key,
        coin_package=package,
        purpose=TimweChargeTransaction.PURPOSE_COIN_PURCHASE,
    )

    coin_transaction = None
    if result.succeeded:
        coin_transaction = fulfil_coin_purchase(result.transaction)
    return result, coin_transaction


def fulfil_coin_purchase(charge):
    """Credit the coins a successful charge paid for, exactly once.

    The claim (setting fulfilled_at) and the credit commit together: if the
    credit fails, the claim rolls back with it, so a charge can never be
    marked fulfilled without its coins, nor credited twice. Returns the
    CoinTransaction, or None when the charge was already fulfilled.
    """
    from api.models.contest import UserCoinBalance

    if charge.coin_package_id is None:
        raise TimweError('This charge did not pay for a coin package.')

    with transaction.atomic():
        claimed = TimweChargeTransaction.objects.filter(
            pk=charge.pk, status='success', fulfilled_at__isnull=True
        ).update(fulfilled_at=timezone.now())
        if not claimed:
            return None

        package = charge.coin_package
        balance, _ = UserCoinBalance.objects.get_or_create(user=charge.user)
        coin_transaction = balance.add_purchased(
            package.get_total_coins(),
            transaction_type='purchase',
            payment_method='airtime',
            package=package,
            # The MA reference, so a coin credit can be traced back to the
            # exact charge TIMWE records -- and reconciled against it.
            payment_reference=charge.reference_code,
            description=f'Airtime purchase: {package.name}'[:255],
            is_successful=True,
        )

    logger.info(
        'TIMWE_CHARGE_FULFILLED',
        extra={
            'operation': 'timwe_charge',
            'reference_code': charge.reference_code,
            'coins': package.get_total_coins(),
        },
    )
    return coin_transaction
