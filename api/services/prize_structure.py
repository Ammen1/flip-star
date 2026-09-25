"""
What each competition pays, and by when.

    tier            winners   prize                    delivery
    Daily Sprint       20     1 GB weekly data         on provisioning
    Weekly Battle      10     1,000 ETB via Telebirr   within 10 days
    Monthly Star        5     5,000 ETB via Telebirr   within 10 days
    Grand Final         1     300,000 ETB via Telebirr within 20 days

The Grand Final winner is also contacted by phone before the payout, which
is why `requires_phone_contact` exists rather than the amount alone deciding
how the win is handled -- 300,000 ETB leaving on a webhook nobody watched is
not something to discover afterwards.

Why this is a table and not settings
------------------------------------
These are contractual figures: what the campaign was advertised as paying.
An admin editing a WinnerGiftPackage row could previously change what a
winner receives, and api/views/crm.py took the payout amount straight from
the **request body** (``amount = request.data.get('amount', 1000)``), so what
a winner was paid depended on what the caller asked for. The amount now comes
from here, and the package row is reconciled against it rather than trusted.

Amounts are Decimal throughout. Money that has passed through a float is
money that no longer adds up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

#: Delivery channels. 'crm' provisions a data bundle through the Ethio
#: Telecom PresentServiceGift API; 'telebirr_b2c' pays cash. Both already
#: exist -- see api/services/crm_service.py and
#: api/integrations/telebirr/direct_debit.py -- and these names match the
#: payment_method values WinnerGiftPackage already uses.
CRM = 'crm'
TELEBIRR = 'telebirr_b2c'

#: One gigabyte, in the megabytes WinnerGiftPackage.amount stores for a data
#: prize. Written out because "1024" on its own in a payout table invites
#: somebody to read it as birr.
ONE_GB_IN_MB = Decimal('1024')


@dataclass(frozen=True)
class PrizeTier:
    """One competition tier's prize, exactly as advertised."""

    tier: str
    winner_count: int
    gift_type: str  # 'data' or 'cash'
    channel: str  # CRM or TELEBIRR
    amount: Decimal  # ETB for cash, MB for data
    description: str
    delivery_days: int | None = None
    requires_phone_contact: bool = False

    @property
    def is_cash(self) -> bool:
        return self.gift_type == 'cash'

    def deadline_from(self, closed_at):
        """When this prize must have been delivered by.

        Measured from the close of the competition, which is what the
        requirement says -- not from when an admin got round to pressing the
        button, which would make the promise meaningless.
        """
        if self.delivery_days is None or closed_at is None:
            return None
        return closed_at + timedelta(days=self.delivery_days)


PRIZES: dict[str, PrizeTier] = {
    'daily': PrizeTier(
        tier='daily',
        winner_count=20,
        gift_type='data',
        channel=CRM,
        amount=ONE_GB_IN_MB,
        description='1 GB weekly data package',
        # The requirement states no deadline for the data prize, only for
        # the three cash tiers. One day is set here as an internal target
        # rather than an advertised promise: provisioning is synchronous, so
        # a bundle that has not landed within a day has failed in a way
        # somebody needs to look at, and without a deadline a stuck data
        # prize would never appear in the overdue list at all. Nothing is
        # promised to winners on the strength of this number -- it exists so
        # that failure is visible.
        delivery_days=1,
    ),
    'weekly': PrizeTier(
        tier='weekly',
        winner_count=10,
        gift_type='cash',
        channel=TELEBIRR,
        amount=Decimal('1000.00'),
        description='1,000 ETB via Telebirr',
        delivery_days=10,
    ),
    'monthly': PrizeTier(
        tier='monthly',
        winner_count=5,
        gift_type='cash',
        channel=TELEBIRR,
        amount=Decimal('5000.00'),
        description='5,000 ETB via Telebirr',
        delivery_days=10,
    ),
    'grand': PrizeTier(
        tier='grand',
        winner_count=1,
        gift_type='cash',
        channel=TELEBIRR,
        amount=Decimal('300000.00'),
        description='300,000 ETB via Telebirr',
        delivery_days=20,
        requires_phone_contact=True,
    ),
}


def prize_for(tier: str) -> PrizeTier:
    """The prize for a tier, or a refusal.

    Deliberately raises rather than returning a default. A tier this table
    does not know about is a bug, and paying out a guessed amount is worse
    than not paying at all.
    """
    try:
        return PRIZES[tier]
    except KeyError:
        raise ValueError(f'No prize defined for competition tier: {tier!r}') from None


def winner_count_for(tier: str) -> int:
    return prize_for(tier).winner_count


def amount_for(tier: str) -> Decimal:
    return prize_for(tier).amount
