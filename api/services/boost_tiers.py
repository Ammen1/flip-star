"""
What a boost costs and what it buys.

    tier       cost   duration   placement           guarantee
    Standard     50       12 h   top of Trending     --
    Premium     100       24 h   top of the feed     --
    Viral     1,000          --  everywhere          5,000 impressions

Why this sits beside the existing boost system rather than replacing it
-----------------------------------------------------------------------
``BoostConfig`` already prices a boost by the hour -- a rate, per-duration
discounts, an impressions-per-coin figure -- and ``BoostCampaign`` already
records start and end times, spends coins through the wallet ledger, tracks
impressions in ``BoostImpression`` and is already read by the Trending feed.
None of that is thrown away. What was missing is the *product*: three named
things a person can buy, at fixed prices, with a stated placement.

So a tier here fixes the inputs the hourly model would otherwise compute,
and the machinery underneath stays exactly as it was.

On "guaranteed" impressions
---------------------------
Only Viral carries a guarantee, and it is a real one: ``BoostImpression``
records a row per viewer with a frequency cap, and
``api/views/boost.py::record_boost_impression`` is what writes it. The
guarantee is a target the platform can actually count against, not a number
printed next to a product. Nothing here marks impressions as guaranteed for
a tier that does not track them -- Standard and Premium carry ``None``, and
the API reports no guarantee for them rather than a zero that reads like
one.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Where a boosted post is lifted.
#:
#: 'trending' is the Trending tab; 'feed' is the home feed, which is this
#: product's personalised surface -- there is no separate "For You" tab, so
#: the home feed is what that name refers to. 'everywhere' lifts in both.
TRENDING = 'trending'
FEED = 'feed'
EVERYWHERE = 'everywhere'

PLACEMENT_LABELS = {
    TRENDING: 'Top of Trending',
    FEED: 'Top of your followers’ feed',
    EVERYWHERE: 'Top of Trending and the feed',
}


@dataclass(frozen=True)
class BoostTier:
    """One purchasable boost."""

    key: str
    label: str
    coins: int
    duration_hours: int
    placement: str
    guaranteed_impressions: int | None = None

    @property
    def has_guarantee(self) -> bool:
        return bool(self.guaranteed_impressions)

    def as_dict(self) -> dict:
        """What the boost sheet shows.

        `guaranteed_impressions` is absent rather than 0 for the tiers
        without one, so a client cannot render "0 guaranteed impressions".
        """
        payload = {
            'key': self.key,
            'label': self.label,
            'coins': self.coins,
            'duration_hours': self.duration_hours,
            'placement': self.placement,
            'placement_label': PLACEMENT_LABELS.get(self.placement, self.placement),
        }
        if self.has_guarantee:
            payload['guaranteed_impressions'] = self.guaranteed_impressions
        return payload


#: Viral runs for a day, but its duration is not what it sells -- the 5,000
#: impressions are. The window exists so the campaign has an end even if the
#: impressions are never served, rather than sitting active for ever.
VIRAL_WINDOW_HOURS = 24

TIERS: dict[str, BoostTier] = {
    'standard': BoostTier(
        key='standard',
        label='Standard',
        coins=50,
        duration_hours=12,
        placement=TRENDING,
    ),
    'premium': BoostTier(
        key='premium',
        label='Premium',
        coins=100,
        duration_hours=24,
        placement=FEED,
    ),
    'viral': BoostTier(
        key='viral',
        label='Viral',
        coins=1000,
        duration_hours=VIRAL_WINDOW_HOURS,
        placement=EVERYWHERE,
        guaranteed_impressions=5000,
    ),
}


def tier_for(key: str) -> BoostTier:
    """The tier `key` names, or a refusal.

    Raises rather than defaulting: an unknown tier is a bug, and charging
    somebody for a guessed one is worse than refusing.
    """
    try:
        return TIERS[str(key).strip().lower()]
    except (KeyError, AttributeError):
        raise ValueError(f'Unknown boost type: {key!r}') from None


def tier_list() -> list[dict]:
    """Every tier, for the boost sheet."""
    return [tier.as_dict() for tier in TIERS.values()]


def placements_for_feed(feed: str) -> tuple[str, ...]:
    """Which placements a given feed should lift.

    Trending lifts 'trending' and 'everywhere'; the home feed lifts 'feed'
    and 'everywhere'. Stated here so the two feeds cannot drift into
    disagreeing about what a placement means.
    """
    if feed == TRENDING:
        return (TRENDING, EVERYWHERE)
    if feed == FEED:
        return (FEED, EVERYWHERE)
    return (TRENDING, FEED, EVERYWHERE)
