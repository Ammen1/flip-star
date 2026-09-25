"""
Who may compete in a campaign, and whether they may post again today.

The rules
---------
A subscriber qualifies for a tier by *showing up and posting*, counted in
distinct days rather than in posts:

    Daily Sprint    posted on the competition day              1 of 1
    Weekly Battle   posted on at least 5 of the 7 days         5 of 7
    Monthly Star    posted on at least 20 of the 30 days      20 of 30
    Grand Final     met Monthly Star in 4 of the 6 months      4 of 6

And a subscriber may enter **one post or video per day** per campaign. A
second entry the same day is refused rather than charged.

Why days and not posts
----------------------
Ten posts on one day is not participation on ten days, and the requirement is
about turning up. Counting posts would let somebody qualify for Monthly Star
in an afternoon.

Why the *local* day
-------------------
``timezone.now()`` is UTC and TIME_ZONE is Africa/Addis_Ababa, three hours
ahead. Grouping by the UTC date puts everything posted between midnight and
03:00 local on the previous day, so a subscriber who posts late most nights
is credited with the wrong days -- and, near a threshold, refused a prize
they had earned. Every boundary here is a local one, the same correction the
daily leaderboard already makes in api/views/campaign_user.py.

What counts
-----------
A ``PostScore`` row: the record written when an entry is accepted into a
campaign. Rejected entries do not count -- a moderated-away post is not
participation -- and this is read from those rows rather than from a counter,
so it cannot drift from what actually happened. Eligibility is never taken
from anything the client sends.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone

#: campaign_type -> (days that must carry a post, days in the period)
REQUIREMENTS: dict[str, tuple[int, int]] = {
    'daily': (1, 1),
    'weekly': (5, 7),
    'monthly': (20, 30),
}

#: Grand Final: qualifying months, out of the campaign's months.
GRAND_MONTHS_REQUIRED = 4
GRAND_MONTHS_TOTAL = 6

#: Entries one subscriber may make per day, per campaign.
MAX_ENTRIES_PER_DAY = 1


@dataclass(frozen=True)
class Eligibility:
    """Whether somebody qualifies, and what is still outstanding if not.

    For Grand Final the unit is months rather than days; the field names stay
    the same so one payload shape serves every level.
    """

    level: str
    days_posted: int
    days_required: int
    days_in_period: int

    @property
    def eligible(self) -> bool:
        return self.days_posted >= self.days_required

    @property
    def days_remaining(self) -> int:
        """Days still needing a post. Zero once qualified."""
        return max(0, self.days_required - self.days_posted)

    def as_dict(self) -> dict:
        """The shape the API hands to the client.

        The client displays this; it never computes it. Eligibility decided on
        the client is eligibility anybody can grant themselves.
        """
        return {
            'level': self.level,
            'eligible': self.eligible,
            'days_posted': self.days_posted,
            'days_required': self.days_required,
            'days_in_period': self.days_in_period,
            'days_remaining': self.days_remaining,
        }


# ── local days ──────────────────────────────────────────────────────────────


def local_date(moment) -> date:
    """The calendar date `moment` fell on, where the subscriber lives."""
    return timezone.localtime(moment).date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """Local midnight to the next local midnight, as aware datetimes."""
    start = timezone.make_aware(datetime.combine(day, time.min))
    return start, start + timedelta(days=1)


def period_days(start, end) -> int:
    """Local days the period covers, counting both ends.

    A campaign running 00:00 Monday to 23:59 Sunday covers seven days, not
    the six a plain subtraction gives.
    """
    if start is None or end is None:
        return 0
    span = local_date(end) - local_date(start)
    return max(0, span.days + 1)


# ── participation ───────────────────────────────────────────────────────────


def participation_days(user, *, campaign=None, start=None, end=None) -> set[date]:
    """The distinct local days this subscriber posted on, within the window.

    A set, so several posts on one day count once -- which is the whole point
    of counting days.
    """
    from api.models.campaign_extended import PostScore

    if user is None or not getattr(user, 'is_authenticated', True):
        return set()

    entries = PostScore.objects.filter(user=user).exclude(moderation_status='rejected')
    if campaign is not None:
        entries = entries.filter(campaign=campaign)
    if start is not None:
        entries = entries.filter(created_at__gte=start)
    if end is not None:
        # Inclusive: entry_deadline is the last moment an entry is accepted,
        # so a post made in that final second still counts.
        entries = entries.filter(created_at__lte=end)

    return {local_date(moment) for moment in entries.values_list('created_at', flat=True)}


def days_posted(user, *, campaign=None, start=None, end=None) -> int:
    return len(participation_days(user, campaign=campaign, start=start, end=end))


def eligibility_for(user, level: str, *, start, end, campaign=None) -> Eligibility:
    """Whether `user` qualifies for `level` over `start`..`end`.

    The period is the campaign's own, so a campaign that ran for three days
    of a week is judged over those three rather than an assumed seven.
    """
    if level not in REQUIREMENTS:
        raise ValueError(f'Unknown campaign level: {level!r}')

    required, nominal_days = REQUIREMENTS[level]
    posted = days_posted(user, campaign=campaign, start=start, end=end)

    # A period shorter than the tier's nominal length cannot demand more days
    # than it contains: a three-day week cannot ask for five. The requirement
    # scales with it rather than being unreachable. A longer one -- a 31-day
    # month -- is still judged against the documented figure.
    actual = period_days(start, end)
    days_in_period = min(nominal_days, actual) if actual else nominal_days
    required = min(required, days_in_period)

    return Eligibility(
        level=level,
        days_posted=posted,
        days_required=required,
        days_in_period=days_in_period,
    )


# ── campaigns ───────────────────────────────────────────────────────────────


def campaign_period(campaign):
    """The window entries are counted over: start to entry deadline.

    entry_deadline rather than voting_end, because posting is what
    eligibility measures and posting closes at the deadline.
    """
    return campaign.start_date, campaign.entry_deadline


def month_periods(start, end):
    """The campaign's calendar months, each clipped to the campaign itself.

    Grand Final asks for Monthly Star in four of six months, so the months
    have to be the ones the monthly campaigns actually ran over.
    """
    if start is None or end is None:
        return []

    periods = []
    cursor = timezone.localtime(start)
    last = timezone.localtime(end)

    while cursor <= last:
        if cursor.month == 12:
            following = cursor.replace(
                year=cursor.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        else:
            following = cursor.replace(
                month=cursor.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
            )

        periods.append((cursor, min(following - timedelta(microseconds=1), last)))
        cursor = following

    return periods


def grand_final_eligibility(user, monthly_periods) -> Eligibility:
    """Qualified for Grand Final: Monthly Star in 4 of the 6 campaign months.

    Measured across every campaign the subscriber posted in during each month
    rather than one campaign -- the Grand Final rewards a season, and the
    season is made of the monthly campaigns that ran inside it.

    A season of fewer than six months is judged on the months it had, so a
    shortened one is not impossible to win.
    """
    periods = list(monthly_periods)
    qualifying = sum(
        1
        for start, end in periods
        if eligibility_for(user, 'monthly', start=start, end=end).eligible
    )

    months = len(periods) or GRAND_MONTHS_TOTAL
    required = min(GRAND_MONTHS_REQUIRED, months)

    return Eligibility(
        level='grand',
        days_posted=qualifying,
        days_required=required,
        days_in_period=months,
    )


def campaign_eligibility(user, campaign) -> Eligibility:
    """Whether `user` qualifies for this campaign, whatever level it is."""
    start, end = campaign_period(campaign)

    if campaign.campaign_type == 'grand':
        return grand_final_eligibility(user, month_periods(start, end))

    return eligibility_for(user, campaign.campaign_type, start=start, end=end, campaign=campaign)


# ── one entry a day ─────────────────────────────────────────────────────────


def entries_today(user, campaign, *, now=None) -> int:
    """Entries this subscriber has already made to this campaign today."""
    from api.models.campaign_extended import PostScore

    start, end = day_bounds(local_date(now or timezone.now()))
    return (
        PostScore.objects.filter(
            user=user, campaign=campaign, created_at__gte=start, created_at__lt=end
        )
        .exclude(moderation_status='rejected')
        .count()
    )


def can_enter_today(user, campaign, *, now=None) -> bool:
    """False once today's single entry has been used."""
    return entries_today(user, campaign, now=now) < MAX_ENTRIES_PER_DAY


def daily_entry_refusal(user, campaign, *, now=None):
    """The response body for a second entry, or None when one is allowed."""
    used = entries_today(user, campaign, now=now)
    if used < MAX_ENTRIES_PER_DAY:
        return None
    return {
        'error': (
            'You have already entered this campaign today. '
            'One post or video per day counts towards the competition.'
        ),
        'code': 'daily_entry_used',
        'entries_today': used,
        'max_per_day': MAX_ENTRIES_PER_DAY,
    }
