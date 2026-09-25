"""
How much one person may give one creator in a day.

    500 coins  ==  5,000 score points  ==  one contributor, one creator, 24 h

The two figures are the same limit counted twice. Coins are what the
contributor spends; score points are what the creator receives, at the gift
weight the campaign scoring uses (10 points per coin gifted --
``CampaignScoringConfig.*_gifts_weight``). Stating both keeps the limit
legible from either side: a contributor sees 500 coins, a leaderboard sees
5,000 points, and neither can drift from the other because one is derived
from the other here.

Why a rolling window and not a calendar day
-------------------------------------------
A daily counter that resets at midnight is two limits: somebody can give
500 coins at 23:55 and 500 more at 00:05, which is 1,000 coins in ten
minutes. The window is the trailing 24 hours from the moment of the request,
which has no seam to sit either side of.

That is also why this does not use ``UserProfile.gifts_sent_today``. That
counter exists, but it counts gifts rather than coins, it is per-sender
rather than per-pair, and nothing resets it on a schedule this module could
rely on.

Why the check has to hold a lock
--------------------------------
Read the total, compare it, then write the gift -- and two requests arriving
together both read the same total and both pass. The pattern is the one in
api/services/concurrency.py: the decision depends on the current value, so
the row the value is derived from has to be locked before it is read.

Here that row is the **sender's coin balance**. It is the one row every
contribution from that sender must touch anyway (``spend_coins`` locks it to
take the coins), so locking it first costs nothing extra and serialises a
sender's concurrent gifts against each other. Two people gifting the same
creator at once are not in conflict -- the limit is per pair, per sender --
so nothing wider needs locking.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

#: Coins one contributor may give one creator in a rolling 24 hours.
DAILY_COIN_LIMIT = 500

#: Score points the creator receives per coin gifted, matching the gift
#: weight in CampaignScoringConfig. 500 coins x 10 = the 5,000 points the
#: requirement states.
POINTS_PER_COIN_GIFTED = 10

#: The same limit, expressed the way a leaderboard sees it.
DAILY_POINT_LIMIT = DAILY_COIN_LIMIT * POINTS_PER_COIN_GIFTED

#: The window. Rolling, from the moment of the request.
WINDOW = timedelta(hours=24)

LIMIT_CODE = 'CONTRIBUTION_LIMIT_REACHED'


def window_start(now=None):
    return (now or timezone.now()) - WINDOW


def contributed_coins(sender, recipient, *, now=None) -> int:
    """Coins this sender has given this creator in the trailing 24 hours.

    Summed from GiftToCreator rows -- the record every contribution path
    writes -- rather than from a counter, so it cannot drift from what
    actually happened and needs no resetting.
    """
    from api.models.contest import GiftToCreator

    if sender is None or recipient is None:
        return 0

    total = GiftToCreator.objects.filter(
        sender=sender,
        recipient=recipient,
        created_at__gte=window_start(now),
    ).aggregate(total=Sum('coins'))['total']

    return int(total or 0)


def contributed_points(sender, recipient, *, now=None) -> int:
    """The same contribution, in the score points the creator received."""
    return contributed_coins(sender, recipient, now=now) * POINTS_PER_COIN_GIFTED


def remaining_coins(sender, recipient, *, now=None) -> int:
    """How much more this sender may give this creator right now."""
    return max(0, DAILY_COIN_LIMIT - contributed_coins(sender, recipient, now=now))


def would_exceed(sender, recipient, coins, *, now=None) -> bool:
    return contributed_coins(sender, recipient, now=now) + int(coins) > DAILY_COIN_LIMIT


def refusal(sender, recipient, coins, *, now=None):
    """The body to return when this contribution is over the limit, or None.

    Carries what was already given and what is left, because "limit reached"
    without a number leaves somebody guessing how long to wait and how much
    they could still send.
    """
    already = contributed_coins(sender, recipient, now=now)
    asked = int(coins)

    if already + asked <= DAILY_COIN_LIMIT:
        return None

    left = max(0, DAILY_COIN_LIMIT - already)
    return {
        'success': False,
        'code': LIMIT_CODE,
        'error': (
            f'You can give {DAILY_COIN_LIMIT} coins to one creator in 24 hours. '
            + (
                f'You have {left} left for this creator today.'
                if left
                else 'You have reached the limit for this creator today.'
            )
        ),
        'limit_coins': DAILY_COIN_LIMIT,
        'limit_points': DAILY_POINT_LIMIT,
        'contributed_coins': already,
        'contributed_points': already * POINTS_PER_COIN_GIFTED,
        'remaining_coins': left,
        'requested_coins': asked,
        'window_hours': int(WINDOW.total_seconds() // 3600),
    }


def lock_sender(sender):
    """Lock the row the limit is decided against. Call inside atomic().

    The sender's coin balance: the one row every contribution from this
    sender touches, so taking it first serialises their concurrent gifts
    without introducing a lock of its own. Returns the locked row, or None
    when the sender has no balance yet -- in which case they have nothing to
    give and the spend will refuse them anyway.
    """
    from api.models.contest import UserCoinBalance

    return UserCoinBalance.objects.select_for_update().filter(user=sender).first()


def status_for(sender, recipient, *, now=None) -> dict:
    """What the gift sheet shows before anything is sent."""
    already = contributed_coins(sender, recipient, now=now)
    return {
        'limit_coins': DAILY_COIN_LIMIT,
        'limit_points': DAILY_POINT_LIMIT,
        'contributed_coins': already,
        'contributed_points': already * POINTS_PER_COIN_GIFTED,
        'remaining_coins': max(0, DAILY_COIN_LIMIT - already),
        'window_hours': int(WINDOW.total_seconds() // 3600),
        'limit_reached': already >= DAILY_COIN_LIMIT,
    }
