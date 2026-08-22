"""
Regression tests for api/tasks/leaderboards.py -- ported from the master
branch. Before this change, current had the Leaderboard/LeaderboardEntry/
WinnerSelection/SelectedWinner models and a Celery Beat schedule entry for
generate_daily_leaderboards etc., but the task functions themselves did not
exist anywhere, so the schedule entries would have errored at run time and
no leaderboard was ever actually generated.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from api.models.campaign import Campaign
from api.models.campaign_extended import Leaderboard, LeaderboardEntry, UserCampaignStats
from api.tasks.leaderboards import (
    auto_select_campaign_winners,
    generate_daily_leaderboards,
    generate_monthly_leaderboards,
    generate_weekly_leaderboards,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def active_daily_campaign(db):
    campaign = Campaign.objects.create(
        title='Daily Campaign', description='x', campaign_type='daily',
        prize_title='Prize', prize_description='x', status='active',
    )
    yield campaign
    campaign.delete()


@pytest.fixture
def two_ranked_users(db, active_daily_campaign):
    u1 = User.objects.create_user(username='leaderboard_u1', password='x')
    u2 = User.objects.create_user(username='leaderboard_u2', password='x')
    UserCampaignStats.objects.create(user=u1, campaign=active_daily_campaign, total_score=100, approved_posts=3)
    UserCampaignStats.objects.create(user=u2, campaign=active_daily_campaign, total_score=50, approved_posts=1)
    yield u1, u2
    u1.delete()
    u2.delete()


def test_generate_daily_leaderboards_creates_ranked_entries(active_daily_campaign, two_ranked_users):
    u1, u2 = two_ranked_users

    result = generate_daily_leaderboards()

    assert 'Generated 1 daily leaderboards' in result
    leaderboard = Leaderboard.objects.get(campaign=active_daily_campaign, period_type='daily')
    assert leaderboard.is_current is True

    entries = list(LeaderboardEntry.objects.filter(leaderboard=leaderboard).order_by('rank'))
    assert [e.user for e in entries] == [u1, u2]
    assert [e.rank for e in entries] == [1, 2]
    assert entries[0].score == 100
    assert entries[1].score == 50


def test_generate_daily_leaderboards_updates_user_campaign_stats_rank(active_daily_campaign, two_ranked_users):
    u1, u2 = two_ranked_users

    generate_daily_leaderboards()

    stat1 = UserCampaignStats.objects.get(user=u1, campaign=active_daily_campaign)
    stat2 = UserCampaignStats.objects.get(user=u2, campaign=active_daily_campaign)
    assert stat1.daily_rank == 1
    assert stat2.daily_rank == 2


def test_generate_daily_leaderboards_is_idempotent_for_the_same_period(active_daily_campaign, two_ranked_users):
    """Running the task twice in the same day must not create a duplicate
    leaderboard snapshot -- the beat schedule can retry/overlap."""
    generate_daily_leaderboards()
    generate_daily_leaderboards()

    assert Leaderboard.objects.filter(campaign=active_daily_campaign, period_type='daily').count() == 1


def test_generate_daily_leaderboards_skips_non_daily_eligible_campaign_types(db):
    """A campaign_type not in the daily-eligible set must be skipped."""
    campaign = Campaign.objects.create(
        title='Irrelevant', description='x', campaign_type='daily', prize_title='p', prize_description='x',
        status='draft',  # not active -- must be skipped regardless of type
    )
    try:
        result = generate_daily_leaderboards()
        assert 'Generated 0 daily leaderboards' in result
        assert not Leaderboard.objects.filter(campaign=campaign).exists()
    finally:
        campaign.delete()


def test_generate_weekly_leaderboards_excludes_daily_only_campaigns(active_daily_campaign, two_ranked_users):
    """generate_weekly_leaderboards must not touch a campaign_type='daily'
    campaign -- weekly is only for weekly/monthly/grand."""
    result = generate_weekly_leaderboards()

    assert 'Generated 0 weekly leaderboards' in result
    assert not Leaderboard.objects.filter(campaign=active_daily_campaign, period_type='weekly').exists()


def test_generate_monthly_leaderboards_only_covers_monthly_and_grand(db):
    weekly_campaign = Campaign.objects.create(
        title='Weekly', description='x', campaign_type='weekly', prize_title='p', prize_description='x', status='active',
    )
    monthly_campaign = Campaign.objects.create(
        title='Monthly', description='x', campaign_type='monthly', prize_title='p', prize_description='x', status='active',
    )
    try:
        generate_monthly_leaderboards()

        assert not Leaderboard.objects.filter(campaign=weekly_campaign, period_type='monthly').exists()
        assert Leaderboard.objects.filter(campaign=monthly_campaign, period_type='monthly').exists()
    finally:
        weekly_campaign.delete()
        monthly_campaign.delete()


def test_auto_select_campaign_winners_is_a_documented_no_op(db):
    """auto_select_campaign_winners only ever looks at period_type='overall'
    leaderboards, which nothing in this codebase creates (see the task's
    own docstring) -- an ended campaign must be left untouched rather than
    erroring."""
    campaign = Campaign.objects.create(
        title='Ended', description='x', campaign_type='daily', prize_title='p', prize_description='x',
        status='active', entry_deadline=timezone.now() - timezone.timedelta(days=1),
    )
    try:
        result = auto_select_campaign_winners()

        assert 'Auto-selected winners for 0 ended campaigns' in result
        campaign.refresh_from_db()
        assert campaign.status == 'active'
        assert campaign.winners_announced is False
    finally:
        campaign.delete()
