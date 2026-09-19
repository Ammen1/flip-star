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
