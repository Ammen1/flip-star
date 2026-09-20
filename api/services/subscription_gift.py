"""
The gift coins a subscriber earns by paying.

This used to be a login reward: open the app, claim 3 coins, keep a streak
alive. It rewarded showing up, which costs nobody anything, and it paid the
same whether or not the account had ever paid for anything. It is now paid
for a *charge*: one gift each time a subscription payment completes. A daily
subscriber is charged daily and is gifted daily; a weekly subscriber is
charged and gifted weekly; a monthly one monthly.

Anchored on SubscriptionPayment, because that is the one row every charge
path writes -- the TIMWE short-code subscribe, the hourly airtime renewal
sweep, the telebirr direct debit, and the SuperApp checkout all create one.
Hooking the payment rather than each of those means a path added later is
covered without anybody remembering to call this.

**Exactly one gift per payment.** The payment's own id is the idempotency
key, held by a unique constraint on the coin ledger rather than by a check in
Python: a webhook delivered twice, a Celery retry and two workers racing all
end with one row, because the second insert is refused by the database. This
is the same reason the renewal charge itself is keyed on its reference code.

Not to be confused with `SubscriptionTier.bonus_coins`, which is a separate,
older reward granted through `SubscriptionPlan.activate()`. That one lands in
the bonus bucket and cannot be spent on gifts; this one is `add_earned`, the
same bucket the login bonus used, so what a subscriber could do with their
daily coins before they can still do.
"""

import logging

from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)

#: The ledger entry these gifts write. Every gift is findable by this alone.
GIFT_TRANSACTION_TYPE = 'subscription_gift'

#: The on-demand package's own coins, granted once at purchase.
ALLOCATION_TRANSACTION_TYPE = 'ondemand_allocation'

#: The plan type whose coins are bought outright rather than earned per period.
ONDEMAND = 'ondemand'

#: Statuses that mean the subscriber actually paid.
PAID = 'completed'


def gift_coins_for(tier) -> int:
    """How many coins one charge on this tier is worth."""
    if tier is None:
        return 0
    return max(0, int(getattr(tier, 'charge_gift_coins', 0) or 0))


def already_gifted(payment) -> bool:
    """Has this payment already paid out? Read-only; the constraint decides."""
    from api.models.contest import CoinTransaction

    return CoinTransaction.objects.filter(
        transaction_type=GIFT_TRANSACTION_TYPE, payment_reference=str(payment.pk)
    ).exists()


def ondemand_allocation(tier):
    """The coins an on-demand package includes, from the package itself.

    `price_coins` is the number the package is configured and sold with --
    "One-time purchase with 100 coins" in the seed. Read straight off the tier
    rather than restated here, so repricing the package in the admin reprices
    what a buyer receives and there is no second number to keep in step.

    Scoped to on-demand deliberately. On the recurring tiers `price_coins` is
    a *price* -- what the plan costs if you pay with coins -- and reading it as
    an allocation there would hand out a month's subscription fee in coins.
    """
    if tier is None or getattr(tier, 'duration_type', None) != ONDEMAND:
        return 0
    return max(0, int(getattr(tier, 'price_coins', 0) or 0))


def grant_ondemand_allocation(payment):
    """Credit the on-demand package's coins. Returns how many.

    Granted **on payment confirmation**, never before: the caller is a signal
    on SubscriptionPayment that fires only for `completed`. Granted **once**:
    the payment is the idempotency key, held by a unique constraint on the
    ledger, so a webhook delivered twice settles for one grant.

    Bonus bucket, not earned. These coins came with a package rather than
    being worked for, and the bonus bucket is the one excluded from
    `giftable_balance` -- so they cannot be cycled straight back out as gifts.
    """
    plan = payment.subscription
    tier = getattr(plan, 'tier', None)
    coins = ondemand_allocation(tier)
    if not coins:
        return 0

    user_id = payment.user_id or getattr(plan, 'user_id', None)
    if not user_id:
        return 0

    from api.models.contest import UserCoinBalance

    try:
        with transaction.atomic():
            balance, _ = UserCoinBalance.objects.get_or_create(user_id=user_id)
            balance.add_bonus(
                coins,
                transaction_type=ALLOCATION_TRANSACTION_TYPE,
                payment_reference=str(payment.pk),
                description=f'{tier.name} package: {coins} coins',
            )
    except IntegrityError:
        logger.info(
            'ONDEMAND_ALLOCATION_ALREADY_GRANTED',
            extra={'payment_id': str(payment.pk), 'user_id': user_id},
        )
        return 0

    logger.info(
        'ONDEMAND_ALLOCATION_GRANTED',
        extra={'payment_id': str(payment.pk), 'user_id': user_id, 'coins': coins},
    )
    return coins


def grant_for_payment(payment) -> int:
    """Give the subscriber the coins this charge earns. Returns how many.

    Returns 0 -- without raising -- when there is nothing to give: the payment
    did not complete, the tier gifts nothing, the plan has no user yet (an SMS
    subscription exists before anybody claims it), or the gift was already
    paid. None of those are errors, and a charge that succeeded must never be
    undone because a reward could not be written.
    """
    if payment is None or payment.status != PAID:
        return 0

    plan = payment.subscription
    tier = getattr(plan, 'tier', None)

    # On-demand is bought outright: its coins come from the package, granted
    # here and once. It does not also earn the per-period gift, which exists
    # to reward a plan being charged again -- an on-demand package never is.
    if getattr(tier, 'duration_type', None) == ONDEMAND:
        return grant_ondemand_allocation(payment)

    # Guard against duplicate grants: if this payment has already gifted coins,
    # do not grant again. The payment id is the idempotency key.
    if already_gifted(payment):
        return 0

    coins = gift_coins_for(tier)
    if not coins:
        return 0

    user_id = payment.user_id or getattr(plan, 'user_id', None)
    if not user_id:
        # An SMS subscription exists before a user claims it: no wallet yet.
        return 0

    from api.models.contest import UserCoinBalance

    try:
        with transaction.atomic():
            balance, _ = UserCoinBalance.objects.get_or_create(user_id=user_id)
            balance.add_earned(
                coins,
                transaction_type=GIFT_TRANSACTION_TYPE,
                payment_reference=str(payment.pk),
                description=f'{tier.name} subscription gift',
            )
    except IntegrityError:
        # The unique constraint refused a second gift for this payment. That
        # is the guard doing its job, not a failure.
        logger.info(
            'SUBSCRIPTION_GIFT_ALREADY_GRANTED',
            extra={'payment_id': str(payment.pk), 'user_id': user_id},
        )
        return 0

    logger.info(
        'SUBSCRIPTION_GIFT_GRANTED',
        extra={'payment_id': str(payment.pk), 'user_id': user_id, 'coins': coins},
    )
    return coins
