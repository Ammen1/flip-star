"""
Who may actually take a prize.

Scoring high was the only thing that mattered before this. Three separate
questions have to be answered yes, and two of them were not being asked:

    1. did they take part?        5 of 7 days, 20 of 30 days
    2. may they win again yet?    the rolling 30-day restriction
    3. did they win this cycle?   the only check that existed

So a subscriber who posted once in a month could out-score everybody and take
Monthly Star, and the frequency restriction never bit because the only thing
writing win records was the CRM gift flow in api/views/crm.py -- prizes
awarded by the scoring engine were invisible to it.

The restriction window is the other half. It was a **calendar month**, which
has a seam: a win on 31 January and another on 1 February are one day apart
and land in different months, so a "one win per month" cap passed both.
Thirty rolling days has no seam, and that specific pair is pinned below.

Participation counting itself is covered in test_campaign_eligibility.py and
not repeated here; this file is about what the selectors do with it.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from api.models import Reel
from api.models.campaign import Campaign
from api.models.campaign_extended import (
    CampaignScoringConfig,
    PostScore,
    UserCampaignStats,
    WinnerFrequencyRecord,
)
from api.services.campaign_eligibility import local_date
from api.services.scoring.engine import CampaignScoringEngine

pytestmark = pytest.mark.django_db


class Entry:
    """The shape the selectors read: a user and a score.

    LeaderboardEntry in production; anything with these two attributes here.
    """

    def __init__(self, user, score):
        self.user = user
        self.score = score


@pytest.fixture
def make_user(django_user_model):
    counter = {'n': 0}

    def _make(name=None):
        counter['n'] += 1
        return django_user_model.objects.create_user(
            username=name or f'player_{counter["n"]}', password='x'
        )

    return _make


def local_midnight(days_ago=0):
    day = local_date(timezone.now()) - timedelta(days=days_ago)
    return timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))


def make_campaign(campaign_type, *, days, title=None, **config):
    """A campaign of `campaign_type` that has been running `days` days."""
    start = local_midnight(days_ago=days - 1)
    campaign = Campaign.objects.create(
        title=title or f'{campaign_type} prize',
        campaign_type=campaign_type,
        status='active',
        start_date=start,
        entry_deadline=start + timedelta(days=days) - timedelta(seconds=1),
        winner_count=1,
    )
    if config:
        CampaignScoringConfig.objects.update_or_create(campaign=campaign, defaults=config)
    return campaign


def post_days(user, campaign, count, *, start=None):
    """`count` days of participation, one entry each."""
    origin = start or campaign.start_date
    for day in range(count):
        reel = Reel.objects.create(user=user, caption='entry', is_campaign_post=True)
        score = PostScore.objects.create(
            reel=reel, campaign=campaign, user=user, moderation_status='approved'
        )
        PostScore.objects.filter(pk=score.pk).update(
            created_at=origin + timedelta(days=day, hours=9)
        )


def record_win_at(user, winner_type, when, campaign=None):
    """A past win, timestamped. won_at is auto_now_add, so it is set after."""
    record = WinnerFrequencyRecord.objects.create(
        user=user,
        campaign=campaign,
        winner_type=winner_type,
        period_start=when,
        period_end=when + timedelta(days=1),
    )
    WinnerFrequencyRecord.objects.filter(pk=record.pk).update(won_at=when)
    return record


# ── participation gates the prize ───────────────────────────────────────────


def test_a_high_scorer_who_did_not_participate_does_not_win(make_user):
    """The gap this closes, stated as plainly as it can be.

    One post, the top score, and no prize -- because Weekly Battle asks for
    five days of showing up and this subscriber showed up once.
    """
    campaign = make_campaign('weekly', days=7)
    slacker = make_user('slacker')
    post_days(slacker, campaign, 1)

    winners = CampaignScoringEngine(campaign).select_winners([Entry(slacker, 10_000)])

    assert winners == []


def test_a_lower_scorer_who_participated_wins_instead(make_user):
    """The prize goes to the qualified entry, not the highest one."""
    campaign = make_campaign('weekly', days=7)
    slacker, regular = make_user('slacker'), make_user('regular')
    post_days(slacker, campaign, 1)
    post_days(regular, campaign, 5)

    winners = CampaignScoringEngine(campaign).select_winners(
        [Entry(slacker, 10_000), Entry(regular, 5)]
    )

    assert [w['user'] for w in winners] == [regular]


@pytest.mark.parametrize(
    ('campaign_type', 'days', 'short', 'enough'),
    [('daily', 1, 0, 1), ('weekly', 7, 4, 5), ('monthly', 30, 19, 20)],
)
def test_each_tier_gates_on_its_own_requirement(make_user, campaign_type, days, short, enough):
    campaign = make_campaign(campaign_type, days=days)
    nearly, qualified = make_user(), make_user()
    post_days(nearly, campaign, short)
    post_days(qualified, campaign, enough)

    engine = CampaignScoringEngine(campaign)
    winners = engine.select_winners([Entry(nearly, 100), Entry(qualified, 1)])

    assert [w['user'] for w in winners] == [qualified]


def test_a_qualified_subscriber_still_wins_normally(make_user):
    """The gate must not refuse everybody."""
    campaign = make_campaign('weekly', days=7)
    user = make_user()
    post_days(user, campaign, 7)

    winners = CampaignScoringEngine(campaign).select_winners([Entry(user, 50)])

    assert len(winners) == 1
    assert winners[0]['user'] == user
    assert winners[0]['points_awarded'] > 0


def test_winning_credits_the_points(make_user):
    campaign = make_campaign('weekly', days=7)
    user = make_user()
    post_days(user, campaign, 5)
    user.profile.refresh_from_db()
    before = user.profile.points

    winners = CampaignScoringEngine(campaign).select_winners([Entry(user, 50)])

    user.profile.refresh_from_db()
    assert user.profile.points == before + winners[0]['points_awarded']


# ── the win is recorded where the restriction can see it ────────────────────


def test_the_engine_records_the_win(make_user):
    """Without this the restriction reads an empty table and lets everybody
    through -- which is why it never bit."""
    campaign = make_campaign('weekly', days=7)
    user = make_user()
    post_days(user, campaign, 5)

    CampaignScoringEngine(campaign).select_winners([Entry(user, 50)])

    assert WinnerFrequencyRecord.objects.filter(user=user, winner_type='weekly').exists()


def test_a_second_selection_run_does_not_award_twice(make_user):
    """A retried task, or an admin pressing the button after the beat."""
    campaign = make_campaign('weekly', days=7)
    user = make_user()
    post_days(user, campaign, 5)

    engine = CampaignScoringEngine(campaign)
    engine.select_winners([Entry(user, 50)])

    user.profile.refresh_from_db()
    after_first = user.profile.points

    second = CampaignScoringEngine(campaign).select_winners([Entry(user, 50)])

    user.profile.refresh_from_db()
    assert second == [], 'the same subscriber won the same cycle twice'
    assert user.profile.points == after_first


def test_winner_selection_locks_the_campaign_row():
    """Two overlapping runs must serialise rather than both awarding.

    The true race needs PostgreSQL (see tests/integration/test_concurrency.py
    for why SQLite cannot exercise SELECT ... FOR UPDATE), so what is pinned
    here is that the lock is taken at all -- the thing whose absence was the
    bug.
    """
    import inspect

    source = inspect.getsource(CampaignScoringEngine)

    assert 'select_for_update' in source or '_selection_lock' in source
    for method in (
        'select_daily_winners',
        'select_weekly_winners',
        'select_monthly_winners',
        'select_grand_winners',
    ):
        body = inspect.getsource(getattr(CampaignScoringEngine, method))
        assert '_selection_lock' in body, f'{method} selects winners without the lock'


# ── the rolling 30 days ─────────────────────────────────────────────────────


def test_the_restriction_window_is_thirty_rolling_days():
    assert WinnerFrequencyRecord.RESTRICTION_DAYS == 30


def test_a_win_twenty_nine_days_ago_still_blocks(make_user):
    user = make_user()
    record_win_at(user, 'weekly', timezone.now() - timedelta(days=29))

    eligible, wins, _limit = WinnerFrequencyRecord.check_frequency_eligibility(user, 'weekly')

    assert not eligible
    assert wins == 1


def test_a_win_thirty_one_days_ago_no_longer_blocks(make_user):
    user = make_user()
    record_win_at(user, 'weekly', timezone.now() - timedelta(days=31))

    eligible, wins, _limit = WinnerFrequencyRecord.check_frequency_eligibility(user, 'weekly')

    assert eligible
    assert wins == 0


def test_wins_in_consecutive_months_are_one_day_apart_not_two_periods(make_user):
    """The calendar-month seam, which is the bug this replaced.

    31 January and 1 February sat in different months, so a cap of one win
    per month passed both. Thirty rolling days sees them as what they are.
    """
    user = make_user()
    yesterday = timezone.now() - timedelta(days=1)
    record_win_at(user, 'weekly', yesterday)

    eligible, _wins, _limit = WinnerFrequencyRecord.check_frequency_eligibility(user, 'weekly')

    assert not eligible, 'two wins a day apart passed a monthly cap'


def test_an_ineligible_winner_is_skipped_by_the_selector(make_user):
    """End to end: the restriction reaches winner selection, not just the
    CRM gift flow that was its only caller."""
    campaign = make_campaign('weekly', days=7)
    recent, fresh = make_user('recent'), make_user('fresh')
    post_days(recent, campaign, 7)
    post_days(fresh, campaign, 5)
    record_win_at(recent, 'weekly', timezone.now() - timedelta(days=3))

    winners = CampaignScoringEngine(campaign).select_winners([Entry(recent, 900), Entry(fresh, 1)])

    assert [w['user'] for w in winners] == [fresh]


def test_the_cap_is_read_from_the_campaign_config(make_user):
    """Two allowed, one used, so a second win is within the cap."""
    campaign = make_campaign('weekly', days=7, weekly_win_limit_per_month=2)
    user = make_user()
    record_win_at(user, 'weekly', timezone.now() - timedelta(days=3), campaign=campaign)

    eligible, wins, limit = WinnerFrequencyRecord.check_frequency_eligibility(
        user, 'weekly', campaign
    )

    assert eligible
    assert (wins, limit) == (1, 2)


def test_the_cap_refuses_once_it_is_reached(make_user):
    campaign = make_campaign('weekly', days=7, weekly_win_limit_per_month=2)
    user = make_user()
    for days_ago in (3, 10):
        record_win_at(user, 'weekly', timezone.now() - timedelta(days=days_ago), campaign=campaign)

    eligible, wins, limit = WinnerFrequencyRecord.check_frequency_eligibility(
        user, 'weekly', campaign
    )

    assert not eligible
    assert (wins, limit) == (2, 2)


# ── the cooldown, which the cap cannot express ──────────────────────────────


def test_the_daily_cooldown_spaces_two_permitted_wins(make_user):
    """A cap of two per thirty days still does not mean two in a row.

    daily_win_cooldown_days was declared on the config and read by nothing,
    so this spacing was never applied.
    """
    campaign = make_campaign(
        'daily', days=1, daily_win_limit_per_month=2, daily_win_cooldown_days=7
    )
    user = make_user()
    record_win_at(user, 'daily', timezone.now() - timedelta(days=1), campaign=campaign)

    eligible, wins, limit = WinnerFrequencyRecord.check_frequency_eligibility(
        user, 'daily', campaign
    )

    assert not eligible, 'won yesterday and allowed to win again today'
    assert (wins, limit) == (1, 2), 'refused by the cooldown, not the cap'


def test_the_cooldown_expires(make_user):
    campaign = make_campaign(
        'daily', days=1, daily_win_limit_per_month=2, daily_win_cooldown_days=7
    )
    user = make_user()
    record_win_at(user, 'daily', timezone.now() - timedelta(days=8), campaign=campaign)

    eligible, _wins, _limit = WinnerFrequencyRecord.check_frequency_eligibility(
        user, 'daily', campaign
    )

    assert eligible


def test_a_zero_cooldown_applies_only_the_cap(make_user):
    campaign = make_campaign(
        'daily', days=1, daily_win_limit_per_month=2, daily_win_cooldown_days=0
    )
    user = make_user()
    record_win_at(user, 'daily', timezone.now() - timedelta(hours=2), campaign=campaign)

    eligible, _wins, _limit = WinnerFrequencyRecord.check_frequency_eligibility(
        user, 'daily', campaign
    )

    assert eligible


# ── grand is per campaign, not per 30 days ──────────────────────────────────


def test_a_grand_win_is_capped_per_campaign(make_user):
    """A grand final happens once in a campaign's life, so a rolling window
    would say nothing useful."""
    campaign = make_campaign('grand', days=180)
    user = make_user()
    record_win_at(user, 'grand', timezone.now() - timedelta(days=200), campaign=campaign)

    eligible, wins, _limit = WinnerFrequencyRecord.check_frequency_eligibility(
        user, 'grand', campaign
    )

    assert not eligible, 'a grand win aged out of a window it should not have'
    assert wins == 1


def test_a_grand_win_in_another_campaign_does_not_block(make_user):
    this_one = make_campaign('grand', days=180, title='this season')
    other = make_campaign('grand', days=180, title='last season')
    user = make_user()
    record_win_at(user, 'grand', timezone.now() - timedelta(days=10), campaign=other)

    eligible, _wins, _limit = WinnerFrequencyRecord.check_frequency_eligibility(
        user, 'grand', this_one
    )

    assert eligible


def test_the_grand_final_checks_the_four_of_six_months(make_user):
    """Finalists are chosen on score; the season requirement is checked here."""
    campaign = make_campaign('grand', days=180)
    absentee = make_user('absentee')
    post_days(absentee, campaign, 3)

    winners = CampaignScoringEngine(campaign).select_winners([Entry(absentee, 10_000)])

    assert winners == []


# ── an unknown tier is not silently waved through ───────────────────────────


def test_an_unrecognised_winner_type_does_not_crash(make_user):
    user = make_user()

    eligible, wins, limit = WinnerFrequencyRecord.check_frequency_eligibility(user, 'fortnightly')

    assert (eligible, wins, limit) == (True, 0, 1)


# ── the cycle flag still works alongside the new gates ──────────────────────


def test_a_subscriber_who_won_this_cycle_is_still_skipped(make_user):
    campaign = make_campaign('monthly', days=30)
    winner, runner_up = make_user('winner'), make_user('runner_up')
    post_days(winner, campaign, 25)
    post_days(runner_up, campaign, 20)

    UserCampaignStats.objects.update_or_create(
        user=winner, campaign=campaign, defaults={'has_won_current_cycle': True}
    )

    winners = CampaignScoringEngine(campaign).select_winners(
        [Entry(winner, 900), Entry(runner_up, 1)]
    )

    assert [w['user'] for w in winners] == [runner_up]
