"""
Points left untouched for 180 days are lost. Coins are not.

That second sentence is the important one. This codebase has an explicit
rule that **coins do not expire** -- pinned by
tests/integration/test_wallet_business_rules.py::test_coins_do_not_expire,
which asserts that no expiry field or method exists on UserCoinBalance or
CoinTransaction. Points are a different thing: they convert to birr, and the
requirement gives them a shelf life. So everything here reads and writes
``UserProfile.points`` and nothing else. A change that expired a coin
balance would break that test, which is exactly what it is for.

What counts as activity
-----------------------
"Inactivity" is measured from what the platform actually recorded, not from
a flag anybody sets:

* the last coin transaction of any kind (earning, spending, buying, being
  gifted) -- CoinTransaction.created_at;
* the last withdrawal request, which is the "withdrawn" half of the rule;
* the last points-to-coins conversion, which is the "converted" half and
  appears in the same ledger as a 'reinvest' transaction;
* the last recorded login.

The most recent of those is the user's last activity. Taking the maximum
rather than picking one means a user who has been active in *any* of these
ways keeps their points -- which is the safe direction to be wrong in, since
the cost of expiring too eagerly is taking money from somebody who was
using the product.

There is no points ledger in this codebase -- ``UserProfile.points`` is a
bare integer with no transaction table behind it -- so there is no single
"last points movement" timestamp to read. The signals above are what exist,
and the CoinTransaction one covers the conversions and gift receipts that
move points in practice. A points ledger would make this exact rather than
inferred; that is worth doing and is noted in the audit rather than
smuggled in here.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Days of inactivity after which unconverted points are lost.
INACTIVITY_DAYS = 180

#: Points at or below this are not worth a notification or a ledger entry;
#: zero is the only value that is genuinely nothing to expire.
MINIMUM_TO_EXPIRE = 1


def cutoff(now=None):
    """The moment before which activity counts as stale."""
    return (now or timezone.now()) - timedelta(days=INACTIVITY_DAYS)


def last_activity_at(user):
    """When this user last did anything the platform recorded, or None.

    None means nothing is on record at all -- a brand-new account, or one
    that has never transacted. Callers treat that as "cannot tell", not as
    "inactive since the beginning of time": expiring on an absence of
    evidence is how a balance disappears for somebody who simply signed up
    before the ledger existed.
    """
    from api.models.contest import CoinTransaction
    from api.models.wallet import WithdrawalRequest

    stamps = []

    last_transaction = (
        CoinTransaction.objects.filter(user=user)
        .order_by('-created_at')
        .values_list('created_at', flat=True)
        .first()
    )
    if last_transaction:
        stamps.append(last_transaction)

    last_withdrawal = (
        WithdrawalRequest.objects.filter(user=user)
        .order_by('-created_at')
        .values_list('created_at', flat=True)
        .first()
    )
    if last_withdrawal:
        stamps.append(last_withdrawal)

    profile = getattr(user, 'profile', None)
    login_date = getattr(profile, 'last_login_date', None)
    if login_date:
        # A DateField; taken as the end of that day so a login today is not
        # read as midnight this morning.
        stamps.append(
            timezone.make_aware(timezone.datetime.combine(login_date, timezone.datetime.max.time()))
        )

    if getattr(user, 'last_login', None):
        stamps.append(user.last_login)

    return max(stamps) if stamps else None


def is_inactive(user, *, now=None) -> bool:
    """Whether this user has been inactive long enough to lose points.

    A user with no recorded activity at all is **not** inactive. See
    last_activity_at: an absence of records is not evidence of absence.
    """
    last = last_activity_at(user)
    if last is None:
        return False
    return last < cutoff(now)


def expirable_points(user, *, now=None) -> int:
    """Points this user would lose if the sweep ran now."""
    profile = getattr(user, 'profile', None)
    points = int(getattr(profile, 'points', 0) or 0)

    if points < MINIMUM_TO_EXPIRE:
        return 0
    if not is_inactive(user, now=now):
        return 0
    return points


def expire_points_for(user, *, now=None) -> int:
    """Take this user's stale points. Returns how many were taken.

    Locked and re-read: the balance is decided by its current value, and a
    conversion or a gift landing between the read and the write would
    otherwise be erased along with the stale total. Strategy 2 in
    api/services/concurrency.py.

    Coins are untouched, deliberately and permanently -- see the module
    docstring.
    """
    from api.models.core import UserProfile

    profile = getattr(user, 'profile', None)
    if profile is None:
        return 0

    with transaction.atomic():
        locked = UserProfile.objects.select_for_update().filter(pk=profile.pk).first()
        if locked is None:
            return 0

        points = int(locked.points or 0)
        if points < MINIMUM_TO_EXPIRE:
            return 0

        # Re-checked under the lock: activity is what decides this, and the
        # check above happened before the lock was held.
        if not is_inactive(locked.user, now=now):
            return 0

        UserProfile.objects.filter(pk=locked.pk).update(points=0)

        # The ledger row goes in the same transaction as the zeroing. This
        # is the one points movement that does not pass through
        # UserProfile._apply_delta -- the balance is taken whole with a
        # direct UPDATE rather than by a delta -- so it writes its own row
        # rather than inheriting one. Expiry is also the movement a user is
        # most likely to dispute, which is the worst one to leave unrecorded.
        from api.models.wallet import PointTransaction

        PointTransaction.objects.create(
            user_id=locked.user_id,
            transaction_type='expiry',
            points=-points,
            balance_after=0,
            description=f'Expired after {INACTIVITY_DAYS} days without activity',
        )

    logger.info(
        'POINTS_EXPIRED user=%s points=%s inactive_since=%s',
        user.pk,
        points,
        last_activity_at(user),
    )
    return points


def candidates(*, now=None):
    """Users whose points are stale enough to be worth checking.

    A cheap first pass: anybody holding points at all. The expensive part --
    working out each one's last activity -- is done per user, so this keeps
    the sweep from loading the whole table.
    """
    from api.models.core import UserProfile

    return UserProfile.objects.filter(points__gte=MINIMUM_TO_EXPIRE).select_related('user')
