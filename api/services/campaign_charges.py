"""
Charging coins for engagement with a campaign post.

Ordering, and why it matters
----------------------------
Every caller runs the action and the charge inside ONE ``transaction.atomic``
block, with the action first::

    with transaction.atomic():
        comment = Comment.objects.create(...)
        charge_engagement(user, reel, 'comment')

That ordering is what makes the two requirements compatible. "Deduct only
after the action succeeds" is satisfied because the row exists before the
charge runs. "If the action fails, do not deduct" is satisfied because an
exception from either statement rolls the whole block back, including the
balance write -- ``spend_coins`` opens a nested atomic, which becomes a
savepoint inside the outer one rather than an independent commit.

The previous code charged BEFORE creating the comment, with no enclosing
block, so a failure between the two left the user paying for nothing.

Duplicate protection
--------------------
``CoinTransaction`` already records user, reel and transaction_type on every
deduction, so it doubles as the idempotency ledger -- no second table, and no
second source of truth about who has paid for what.

Like was already safe by accident: ``Vote.objects.get_or_create`` means the
charge only runs when a vote is genuinely new. Share had nothing, so every
double-tap, retry and refresh deducted again. ``once=True`` closes that by
checking the ledger under the same lock that guards the balance.

Costs are configuration
-----------------------
All of them live on WalletConfig and default to 0, which means the feature is
off until an operator turns it on. A cost of 0 is not "free by accident" -- it
is the documented way to disable charging for an action, so this module treats
it as "do nothing" rather than as a misconfiguration to warn about.
"""

from __future__ import annotations

from django.db import transaction

#: action -> (WalletConfig field for campaign posts, field for ordinary posts,
#:            CoinTransaction.transaction_type)
#:
#: Two fields per action because the pricing model distinguishes campaign
#: engagement from ordinary engagement; the caller does not have to know which
#: applies, it just passes the reel.
_ACTIONS = {
    'like': ('cost_like', 'cost_like_non_campaign', 'campaign_like'),
    'comment': ('cost_comment', 'cost_comment_non_campaign', 'campaign_comment'),
    'share': ('cost_share', 'cost_share_non_campaign', 'campaign_share'),
    'post': ('cost_post_create', 'cost_post_create_non_campaign', 'campaign_join'),
}


class InsufficientCoins(Exception):
    """Raised when the balance cannot cover a charge.

    Carries the numbers so the view can build its response without re-reading
    the balance -- a second read outside the lock could report a different
    figure than the one the refusal was based on.
    """

    def __init__(self, required, available, message):
        super().__init__(message)
        self.required = required
        self.available = available
        self.message = message


def engagement_cost(reel, action: str) -> int:
    """Coins this action costs on this reel, or 0 when charging is disabled."""
    if action not in _ACTIONS:
        raise ValueError(f'Unknown engagement action: {action!r}')

    from api.models.wallet import WalletConfig

    campaign_field, ordinary_field, _ = _ACTIONS[action]
    config = WalletConfig.get_config()
    field = campaign_field if getattr(reel, 'is_campaign_post', False) else ordinary_field
    return getattr(config, field, 0) or 0


def already_charged(user, reel, action: str) -> bool:
    """True when this user has already paid for this action on this reel."""
    from api.models.contest import CoinTransaction

    _, _, tx_type = _ACTIONS[action]
    return CoinTransaction.objects.filter(
        user=user,
        reel=reel,
        transaction_type=tx_type,
        is_successful=True,
    ).exists()


def charge_engagement(user, reel, action: str, *, once: bool = False, description: str = ''):
    """Deduct the configured cost, or do nothing when there is nothing to charge.

    Returns the number of coins actually taken, so a caller can report it.

    ``once=True`` makes the charge idempotent for this (user, reel, action):
    a repeat is a no-op returning 0 rather than an error, because from the
    user's point of view the action did happen -- they simply are not billed
    twice for it. Use it wherever the action itself has no natural uniqueness
    constraint, which today means share.

    Never charges a user for their own post, and never charges an
    unauthenticated request.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return 0
    if reel.user_id == user.id:
        return 0

    cost = engagement_cost(reel, action)
    if cost <= 0:
        return 0

    from api.models.contest import UserCoinBalance

    _, _, tx_type = _ACTIONS[action]
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)

    # The ledger check has to happen while holding the balance row, not before
    # taking it. Checked outside the lock, two simultaneous shares both find no
    # prior transaction, both proceed, and the user is charged twice -- which
    # is the exact failure `once` exists to prevent, reintroduced one layer
    # down. Locking first makes the second request wait until the first has
    # committed its CoinTransaction, so it then sees it and returns 0.
    #
    # spend_coins takes the same row lock again below; re-acquiring a lock
    # already held in this transaction is free.
    with transaction.atomic():
        UserCoinBalance.objects.select_for_update().get(pk=balance.pk)

        if once and already_charged(user, reel, action):
            return 0

        return _spend(balance, cost, tx_type, reel, action, description)


def _spend(balance, cost, tx_type, reel, action, description):
    """Perform the deduction, translating the failure into InsufficientCoins."""
    try:
        balance.spend_coins(
            cost,
            tx_type,
            reel=reel,
            description=description or f'{action.title()} on campaign post #{reel.id}',
        )
    except ValueError as exc:
        # Re-read under no lock is fine here: the charge did not happen, so
        # the figure shown to the user is the one that was insufficient.
        raise InsufficientCoins(cost, balance.balance, str(exc)) from exc

    return cost


@transaction.atomic
def charge_for_action(user, reel, action: str, *, once: bool = False, description: str = ''):
    """Standalone charge for callers with no action of their own to wrap.

    Prefer inlining ``charge_engagement`` inside the block that performs the
    action -- that is what ties the two together. This exists for the case
    where the action has already been committed elsewhere and cannot be moved.
    """
    return charge_engagement(user, reel, action, once=once, description=description)
