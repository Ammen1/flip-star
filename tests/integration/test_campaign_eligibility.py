"""
Who qualifies for a campaign, and the one-entry-a-day cap.

    Daily Sprint    posted on the competition day              1 of 1
    Weekly Battle   posted on at least 5 of the 7 days         5 of 7
    Monthly Star    posted on at least 20 of the 30 days      20 of 30
    Grand Final     met Monthly Star in 4 of the 6 months      4 of 6

None of this was enforced before: days_participated fed a bonus-point
calculation and nothing gated entry, so a subscriber who posted once in a
month was as eligible for Monthly Star as one who posted on twenty-five days.

The rules turn on **distinct local days**, which is where the bugs live. Two
of them are pinned here specifically:

* several posts on one day counting as several days, which would let somebody
  qualify for Monthly Star in an afternoon; and
* the UTC/local split. TIME_ZONE is Africa/Addis_Ababa, timezone.now() is UTC,
  and a post made at 01:00 local falls on the previous UTC date. Counting UTC
  days silently miscounts for anyone who posts late -- and near a threshold
  that is the difference between winning and being refused.

Boundaries are asserted with real timestamps rather than mocks, because the
thing being tested *is* the date arithmetic.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from api.models import Reel
from api.models.campaign import Campaign
from api.models.campaign_extended import PostScore
from api.services.campaign_eligibility import (
    MAX_ENTRIES_PER_DAY,
    REQUIREMENTS,
    campaign_eligibility,
    can_enter_today,
    daily_entry_refusal,
    days_posted,
    eligibility_for,
    entries_today,
    grand_final_eligibility,
    local_date,
    month_periods,
    participation_days,
    period_days,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username='contender', password='x')


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(username='rival', password='x')


def make_campaign(campaign_type, *, start, end, title=None):
    return Campaign.objects.create(
        title=title or f'{campaign_type} campaign',
        campaign_type=campaign_type,
        status='active',
        start_date=start,
        entry_deadline=end,
    )


def post_on(user, campaign, moment, *, moderation_status='approved'):
    """An entry timestamped `moment`.

    created_at is auto_now_add, so it is set after the fact with an UPDATE --
    the only way to place an entry on a chosen day.
    """
    reel = Reel.objects.create(user=user, caption='entry', is_campaign_post=True)
    score = PostScore.objects.create(
        reel=reel,
        campaign=campaign,
        user=user,
        moderation_status=moderation_status,
    )
    PostScore.objects.filter(pk=score.pk).update(created_at=moment)
    score.refresh_from_db()
    return score


def local_midnight(days_ago=0):
    """Local midnight, `days_ago` days back -- an unambiguous day anchor."""
    day = local_date(timezone.now()) - timedelta(days=days_ago)
    return timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))


# ── the documented requirements ─────────────────────────────────────────────


def test_the_requirements_are_what_the_product_promised():
    """The figures themselves, pinned away from the logic that applies them."""
    assert REQUIREMENTS['daily'] == (1, 1)
    assert REQUIREMENTS['weekly'] == (5, 7)
    assert REQUIREMENTS['monthly'] == (20, 30)


def test_one_entry_a_day_is_the_cap():
    assert MAX_ENTRIES_PER_DAY == 1


# ── Daily Sprint: post on the day ───────────────────────────────────────────


def test_a_daily_sprint_needs_one_post_on_the_day(user):
    start = local_midnight()
    campaign = make_campaign('daily', start=start, end=start + timedelta(hours=23, minutes=59))

    assert not campaign_eligibility(user, campaign).eligible

    post_on(user, campaign, start + timedelta(hours=10))

    assert campaign_eligibility(user, campaign).eligible


def test_a_daily_sprint_without_a_post_is_not_eligible(user):
    start = local_midnight()
    campaign = make_campaign('daily', start=start, end=start + timedelta(hours=23, minutes=59))

    result = campaign_eligibility(user, campaign)

    assert result.days_posted == 0
    assert result.days_required == 1
    assert result.days_remaining == 1


# ── Weekly Battle: 5 of 7 ───────────────────────────────────────────────────


@pytest.fixture
def week(user):
    """A seven-day campaign that started six days ago and ends tonight."""
    start = local_midnight(days_ago=6)
    return make_campaign(
        'weekly', start=start, end=start + timedelta(days=7) - timedelta(seconds=1)
    )


@pytest.mark.parametrize(('days', 'eligible'), [(0, False), (4, False), (5, True), (7, True)])
def test_the_weekly_battle_turns_on_five_days(user, week, days, eligible):
    for day in range(days):
        post_on(user, week, week.start_date + timedelta(days=day, hours=9))

    assert campaign_eligibility(user, week).eligible is eligible


def test_four_days_of_posting_falls_one_short(user, week):
    """The near miss, reported so the client can say what is outstanding."""
    for day in range(4):
        post_on(user, week, week.start_date + timedelta(days=day, hours=9))

    result = campaign_eligibility(user, week)

    assert result.days_posted == 4
    assert result.days_required == 5
    assert result.days_remaining == 1
    assert not result.eligible


def test_posting_five_times_in_one_day_is_one_day(user, week):
    """The rule counts turning up, not volume.

    Counting posts rather than days would make this eligible on day one,
    which is the whole loophole the day-counting exists to close.
    """
    for hour in (6, 9, 12, 15, 18):
        post_on(user, week, week.start_date + timedelta(hours=hour))

    result = campaign_eligibility(user, week)

    assert result.days_posted == 1
    assert not result.eligible


def test_the_five_days_need_not_be_consecutive(user, week):
    """Nothing in the requirement asks for a streak."""
    for day in (0, 2, 3, 5, 6):
        post_on(user, week, week.start_date + timedelta(days=day, hours=9))

    assert campaign_eligibility(user, week).eligible


# ── Monthly Star: 20 of 30 ──────────────────────────────────────────────────


@pytest.fixture
def month(user):
    start = local_midnight(days_ago=29)
    return make_campaign(
        'monthly', start=start, end=start + timedelta(days=30) - timedelta(seconds=1)
    )


@pytest.mark.parametrize(('days', 'eligible'), [(0, False), (19, False), (20, True), (30, True)])
def test_the_monthly_star_turns_on_twenty_days(user, month, days, eligible):
    for day in range(days):
        post_on(user, month, month.start_date + timedelta(days=day, hours=9))

    assert campaign_eligibility(user, month).eligible is eligible


def test_nineteen_days_is_not_twenty(user, month):
    for day in range(19):
        post_on(user, month, month.start_date + timedelta(days=day, hours=9))

    result = campaign_eligibility(user, month)

    assert result.days_posted == 19
    assert result.days_remaining == 1
    assert not result.eligible


# ── Grand Final: Monthly Star in 4 of 6 months ──────────────────────────────


def qualifying_month(user, campaign, month_start):
    """Twenty days of posting inside one month."""
    for day in range(20):
        post_on(user, campaign, month_start + timedelta(days=day, hours=9))


@pytest.mark.parametrize(('months', 'eligible'), [(0, False), (3, False), (4, True), (6, True)])
def test_the_grand_final_turns_on_four_qualifying_months(user, months, eligible):
    start = local_midnight(days_ago=200)
    campaign = make_campaign('monthly', start=start, end=timezone.now())

    periods = []
    for index in range(6):
        month_start = start + timedelta(days=31 * index)
        periods.append((month_start, month_start + timedelta(days=30)))
        if index < months:
            qualifying_month(user, campaign, month_start)

    assert grand_final_eligibility(user, periods).eligible is eligible


def test_a_month_with_nineteen_days_does_not_count_towards_the_grand_final(user):
    """Each month is judged by the Monthly Star rule, not by a weaker one."""
    start = local_midnight(days_ago=200)
    campaign = make_campaign('monthly', start=start, end=timezone.now())

    periods = []
    for index in range(6):
        month_start = start + timedelta(days=31 * index)
        periods.append((month_start, month_start + timedelta(days=30)))
        for day in range(19):  # one short, every month
            post_on(user, campaign, month_start + timedelta(days=day, hours=9))

    result = grand_final_eligibility(user, periods)

    assert result.days_posted == 0
    assert not result.eligible


def test_a_grand_campaign_splits_itself_into_months(user):
    """campaign_eligibility dispatches a grand campaign to the months it ran."""
    start = local_midnight(days_ago=170)
    campaign = make_campaign('grand', start=start, end=timezone.now())

    result = campaign_eligibility(user, campaign)

    assert result.level == 'grand'
    assert result.days_required == 4
    assert result.days_in_period >= 5


def test_month_periods_covers_the_span_without_gaps_or_overlap():
    start = timezone.make_aware(timezone.datetime(2026, 1, 15, 0, 0))
    end = timezone.make_aware(timezone.datetime(2026, 6, 20, 23, 59))

    periods = month_periods(start, end)

    assert len(periods) == 6
    assert periods[0][0] == timezone.localtime(start)
    assert periods[-1][1] == timezone.localtime(end)
    for (_, earlier_end), (later_start, _) in zip(periods, periods[1:], strict=False):
        assert earlier_end < later_start
        assert (later_start - earlier_end) <= timedelta(seconds=1)


# ── time boundaries ─────────────────────────────────────────────────────────


def test_a_post_just_before_local_midnight_counts_for_that_day(user, week):
    """23:59:59 local is still today."""
    day = week.start_date + timedelta(days=1)
    post_on(user, week, day + timedelta(hours=23, minutes=59, seconds=59))

    assert local_date(day) in participation_days(user, campaign=week)


def test_a_post_just_after_local_midnight_counts_for_the_new_day(user, week):
    """00:00:01 local is tomorrow -- and, in UTC, still yesterday.

    This is the bug the local-day handling exists for. Under UTC grouping
    both posts below land on the same date and the subscriber is credited
    with one day instead of two.
    """
    day_one = week.start_date + timedelta(days=1, hours=23)
    day_two = week.start_date + timedelta(days=2, seconds=1)

    post_on(user, week, day_one)
    post_on(user, week, day_two)

    days = participation_days(user, campaign=week)
    assert local_date(day_one) in days
    assert local_date(day_two) in days
    assert len(days) == 2


def test_two_posts_either_side_of_utc_midnight_are_one_local_day(user, week):
    """The mirror image: 01:00 and 04:00 local are one day locally and two in
    UTC. Counting UTC days would over-credit here as surely as it
    under-credits above."""
    day = week.start_date + timedelta(days=3)

    post_on(user, week, day + timedelta(hours=1))
    post_on(user, week, day + timedelta(hours=4))

    assert len(participation_days(user, campaign=week)) == 1


def test_a_post_before_the_campaign_started_does_not_count(user, week):
    post_on(user, week, week.start_date - timedelta(days=1))

    assert days_posted(user, campaign=week, start=week.start_date, end=week.entry_deadline) == 0


def test_a_post_after_the_entry_deadline_does_not_count(user, week):
    post_on(user, week, week.entry_deadline + timedelta(hours=2))

    assert days_posted(user, campaign=week, start=week.start_date, end=week.entry_deadline) == 0


def test_a_post_in_the_deadline_s_final_second_still_counts(user, week):
    """The deadline is the last moment an entry is accepted, so an entry made
    at that moment is inside the period, not outside it."""
    post_on(user, week, week.entry_deadline)

    assert days_posted(user, campaign=week, start=week.start_date, end=week.entry_deadline) == 1


# ── partial periods ─────────────────────────────────────────────────────────


def test_a_week_that_only_ran_three_days_cannot_demand_five(user):
    """A shortened campaign scales its requirement rather than being
    impossible to qualify for."""
    start = local_midnight(days_ago=2)
    campaign = make_campaign(
        'weekly', start=start, end=start + timedelta(days=3) - timedelta(seconds=1)
    )

    for day in range(3):
        post_on(user, campaign, start + timedelta(days=day, hours=9))

    result = campaign_eligibility(user, campaign)

    assert result.days_in_period == 3
    assert result.days_required == 3
    assert result.eligible


def test_a_thirty_one_day_month_still_asks_for_twenty(user):
    """A longer period does not inflate the documented requirement."""
    start = local_midnight(days_ago=30)
    campaign = make_campaign(
        'monthly', start=start, end=start + timedelta(days=31) - timedelta(seconds=1)
    )

    result = campaign_eligibility(user, campaign)

    assert result.days_required == 20
    assert result.days_in_period == 30


def test_a_period_counts_both_its_end_days():
    """Monday 00:00 to Sunday 23:59 is seven days, not six."""
    start = local_midnight(days_ago=6)
    assert period_days(start, start + timedelta(days=7) - timedelta(seconds=1)) == 7
    assert period_days(start, start) == 1


def test_a_campaign_with_no_dates_falls_back_to_the_documented_period(user):
    """An unscheduled campaign is judged against the tier's own figures
    rather than dividing by a period of zero."""
    campaign = make_campaign('weekly', start=None, end=None)

    result = campaign_eligibility(user, campaign)

    assert result.days_in_period == 7
    assert result.days_required == 5


# ── what counts, and whose ──────────────────────────────────────────────────


def test_a_rejected_post_is_not_participation(user, week):
    """A moderated-away entry cannot buy eligibility."""
    for day in range(5):
        post_on(
            user, week, week.start_date + timedelta(days=day, hours=9), moderation_status='rejected'
        )

    result = campaign_eligibility(user, week)

    assert result.days_posted == 0
    assert not result.eligible


def test_a_pending_post_counts_while_it_waits(user, week):
    """Moderation runs behind posting; a subscriber must not lose a day they
    turned up for because nobody has reviewed it yet. Only an outright
    rejection removes the day."""
    for day in range(5):
        post_on(
            user, week, week.start_date + timedelta(days=day, hours=9), moderation_status='pending'
        )

    assert campaign_eligibility(user, week).eligible


def test_another_subscriber_s_posts_do_not_make_you_eligible(user, other_user, week):
    for day in range(7):
        post_on(other_user, week, week.start_date + timedelta(days=day, hours=9))

    assert campaign_eligibility(user, week).days_posted == 0


def test_posts_in_a_different_campaign_do_not_count(user, week):
    """Per-campaign eligibility stays per-campaign."""
    start = local_midnight(days_ago=6)
    elsewhere = make_campaign('weekly', start=start, end=timezone.now(), title='another battle')

    for day in range(7):
        post_on(user, elsewhere, start + timedelta(days=day, hours=9))

    assert campaign_eligibility(user, week).days_posted == 0


def test_eligibility_is_read_from_post_records_not_a_counter(user, week):
    """Requirement: computed from authoritative backend records.

    UserCampaignStats carries a total_posts field that anything could write.
    Eligibility must not be derived from it, so a wrong or stale counter
    cannot grant a prize.
    """
    from api.models.campaign_extended import UserCampaignStats

    stats, _ = UserCampaignStats.objects.get_or_create(user=user, campaign=week)
    UserCampaignStats.objects.filter(pk=stats.pk).update(total_posts=999, approved_posts=999)

    assert not campaign_eligibility(user, week).eligible


# ── one entry a day ─────────────────────────────────────────────────────────


def test_the_first_entry_of_the_day_is_allowed(user, week):
    assert can_enter_today(user, week)
    assert daily_entry_refusal(user, week) is None


def test_a_second_entry_the_same_day_is_refused(user, week):
    post_on(user, week, timezone.now())

    assert not can_enter_today(user, week)

    refusal = daily_entry_refusal(user, week)
    assert refusal is not None
    assert refusal['code'] == 'daily_entry_used'
    assert refusal['entries_today'] == 1
    assert refusal['max_per_day'] == 1


def test_yesterday_s_entry_does_not_block_today(user, week):
    post_on(user, week, timezone.now() - timedelta(days=1))

    assert entries_today(user, week) == 0
    assert can_enter_today(user, week)


def test_the_cap_is_per_campaign(user, week):
    """Entering one campaign today must not lock the subscriber out of
    another running alongside it."""
    other = make_campaign(
        'daily', start=local_midnight(), end=timezone.now() + timedelta(hours=1), title='sprint'
    )
    post_on(user, week, timezone.now())

    assert not can_enter_today(user, week)
    assert can_enter_today(user, other)


def test_the_cap_is_per_subscriber(user, other_user, week):
    post_on(other_user, week, timezone.now())

    assert can_enter_today(user, week)


def test_a_rejected_entry_does_not_use_up_the_day(user, week):
    """Refusing a second entry after the first was moderated away would cost
    the subscriber the day for a post nobody is scoring."""
    post_on(user, week, timezone.now(), moderation_status='rejected')

    assert can_enter_today(user, week)


def test_the_cap_uses_the_local_day_not_the_utc_one(user, week):
    """An entry at 01:00 local is today's, though UTC still calls it
    yesterday. Grouping by UTC would let somebody post twice between local
    midnight and 03:00."""
    today = local_midnight()
    post_on(user, week, today + timedelta(hours=1))

    assert entries_today(user, week) == 1
    assert not can_enter_today(user, week)


def test_an_entry_late_yesterday_evening_does_not_count_as_today(user, week):
    post_on(user, week, local_midnight() - timedelta(minutes=1))

    assert entries_today(user, week) == 0


# ── the level payload ───────────────────────────────────────────────────────


def test_the_payload_says_what_is_still_outstanding(user, week):
    for day in range(2):
        post_on(user, week, week.start_date + timedelta(days=day, hours=9))

    payload = campaign_eligibility(user, week).as_dict()

    assert payload == {
        'level': 'weekly',
        'eligible': False,
        'days_posted': 2,
        'days_required': 5,
        'days_in_period': 7,
        'days_remaining': 3,
    }


def test_a_qualified_subscriber_has_nothing_outstanding(user, week):
    for day in range(6):
        post_on(user, week, week.start_date + timedelta(days=day, hours=9))

    payload = campaign_eligibility(user, week).as_dict()

    assert payload['eligible']
    assert payload['days_remaining'] == 0, 'a surplus must not report negative days'


def test_an_unknown_level_is_refused_rather_than_guessed(user, week):
    with pytest.raises(ValueError, match='Unknown campaign level'):
        eligibility_for(user, 'fortnightly', start=week.start_date, end=week.entry_deadline)
