"""
Regression tests for global_leaderboard (api/views/campaign_user.py) --
ported from the master branch, entirely missing in the current project
before this change.

Uses the real `db` fixture -- see tests/conftest.py's MIGRATIONS_ARE_REPLAYABLE.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.utils import timezone

from api.models.campaign import Campaign
from api.models.campaign_extended import PostScore
from api.models.core import Reel, Vote
from api.views.campaign_user import global_leaderboard

pytestmark = pytest.mark.integration

factory = RequestFactory()


@pytest.fixture
def daily_campaign(db):
    campaign = Campaign.objects.create(
        title='Daily Leaderboard Campaign',
        description='x',
        campaign_type='daily',
        prize_title='p',
        prize_description='x',
        status='active',
        start_date=timezone.now(),
    )
    yield campaign
    campaign.delete()


@pytest.fixture
def two_scored_users(db, daily_campaign):
    u1 = User.objects.create_user(username='glb_leader_u1', password='x')
    u2 = User.objects.create_user(username='glb_leader_u2', password='x')

    reel1 = Reel.objects.create(user=u1, caption='r1')
    reel2 = Reel.objects.create(user=u2, caption='r2')
    PostScore.objects.create(reel=reel1, campaign=daily_campaign, user=u1)
    PostScore.objects.create(reel=reel2, campaign=daily_campaign, user=u2)

    # u1 gets 2 likes, u2 gets 0 -- u1 should outrank u2.
    voter1 = User.objects.create_user(username='glb_voter1', password='x')
    voter2 = User.objects.create_user(username='glb_voter2', password='x')
    Vote.objects.create(user=voter1, reel=reel1)
    Vote.objects.create(user=voter2, reel=reel1)

    yield u1, u2
    voter1.delete()
    voter2.delete()
    reel1.delete()
    reel2.delete()
    u1.delete()
    u2.delete()


def test_daily_leaderboard_ranks_by_score(daily_campaign, two_scored_users):
    u1, u2 = two_scored_users
    # The subscriber's day, which is what the view now windows on.
    today = timezone.localtime(timezone.now()).strftime('%Y-%m-%d')
    request = factory.get(f'/leaderboard/global/?period=daily&date={today}')

    response = global_leaderboard(request)

    assert response.status_code == 200, response.data
    assert response.data['period'] == 'daily'
    campaign_block = next(
        c for c in response.data['campaigns'] if c['campaign_id'] == daily_campaign.id
    )
    leaders = campaign_block['leaders']
    assert [entry['username'] for entry in leaders] == ['glb_leader_u1', 'glb_leader_u2']
    assert leaders[0]['rank'] == 1
    assert leaders[0]['likes_count'] == 2
    assert leaders[1]['likes_count'] == 0


def test_daily_leaderboard_excludes_rejected_posts(db, daily_campaign):
    u = User.objects.create_user(username='glb_rejected_user', password='x')
    reel = Reel.objects.create(user=u, caption='rejected post')
    PostScore.objects.create(
        reel=reel, campaign=daily_campaign, user=u, moderation_status='rejected'
    )
    try:
        # The subscriber's day, which is what the view now windows on.
        today = timezone.localtime(timezone.now()).strftime('%Y-%m-%d')
        request = factory.get(f'/leaderboard/global/?period=daily&date={today}')

        response = global_leaderboard(request)

        assert response.status_code == 200
        assert not any(c['campaign_id'] == daily_campaign.id for c in response.data['campaigns'])
    finally:
        reel.delete()
        u.delete()


def test_weekly_leaderboard_aggregates_across_daily_campaigns(daily_campaign, two_scored_users):
    request = factory.get('/leaderboard/global/?period=weekly')

    response = global_leaderboard(request)

    assert response.status_code == 200, response.data
    assert response.data['period'] == 'weekly'
    usernames = [entry['username'] for entry in response.data['leaders']]
    assert 'glb_leader_u1' in usernames
    assert 'glb_leader_u2' in usernames


def test_monthly_leaderboard_returns_empty_leaders_with_no_data(db):
    request = factory.get('/leaderboard/global/?period=monthly')

    response = global_leaderboard(request)

    assert response.status_code == 200
    assert response.data['period'] == 'monthly'
    assert response.data['leaders'] == []


def test_grand_leaderboard_returns_empty_leaders_with_no_data(db):
    request = factory.get('/leaderboard/global/?period=grand')

    response = global_leaderboard(request)

    assert response.status_code == 200
    assert response.data['period'] == 'grand'
    assert response.data['leaders'] == []


def test_invalid_period_returns_400(db):
    request = factory.get('/leaderboard/global/?period=nonsense')

    response = global_leaderboard(request)

    assert response.status_code == 400


def test_unknown_master_campaign_id_returns_404(db):
    request = factory.get('/leaderboard/global/?period=daily&master_campaign_id=99999999')

    response = global_leaderboard(request)

    assert response.status_code == 404


# ── the day is the subscriber's day, not UTC's ──────────────────────────────
#
# TIME_ZONE is Africa/Addis_Ababa, three hours ahead of UTC, and
# timezone.now() is UTC. The view took its default date off `now` and built
# the window with `tzinfo=now.tzinfo`, so "today" ran 03:00 to 03:00 local.
#
# Between midnight and 3am that had two effects at once: the board defaulted
# to yesterday's date, and anything posted since local midnight fell into a
# window nobody was looking at yet. At 02:00 the daily leaderboard was simply
# empty of the night's posts -- which is what "the leaderboard is not working"
# looks like from the app.


def _post_at(campaign, when, username):
    """A scored post at a given instant."""
    user = User.objects.create_user(username=username, password='x')
    reel = Reel.objects.create(user=user, caption='r')
    score = PostScore.objects.create(reel=reel, campaign=campaign, user=user)
    # created_at is auto_now_add, so it has to be set after the fact.
    PostScore.objects.filter(pk=score.pk).update(created_at=when)
    return user, reel


def test_a_post_just_after_local_midnight_is_on_todays_board(db, daily_campaign):
    """The exact case that was invisible: 00:30 local, today."""
    from datetime import datetime, timedelta

    local_today = timezone.localtime(timezone.now()).date()
    just_after_midnight = timezone.make_aware(
        datetime.combine(local_today, datetime.min.time())
    ) + timedelta(minutes=30)

    user, reel = _post_at(daily_campaign, just_after_midnight, 'glb_midnight_u1')
    try:
        request = factory.get(f'/leaderboard/global/?period=daily&date={local_today}')

        response = global_leaderboard(request)

        assert response.status_code == 200, response.data
        block = next(c for c in response.data['campaigns'] if c['campaign_id'] == daily_campaign.id)
        assert 'glb_midnight_u1' in [e['username'] for e in block['leaders']]
    finally:
        reel.delete()
        user.delete()


def test_the_window_is_local_midnight_to_local_midnight(db, daily_campaign):
    """A post at 23:30 local belongs to that day, not the next one."""
    from datetime import datetime, timedelta

    local_today = timezone.localtime(timezone.now()).date()
    late_last_night = timezone.make_aware(
        datetime.combine(local_today, datetime.min.time())
    ) - timedelta(minutes=30)

    user, reel = _post_at(daily_campaign, late_last_night, 'glb_late_u1')
    try:
        today = factory.get(f'/leaderboard/global/?period=daily&date={local_today}')
        yesterday_date = local_today - timedelta(days=1)
        yesterday = factory.get(f'/leaderboard/global/?period=daily&date={yesterday_date}')

        on_today = [
            e['username']
            for c in global_leaderboard(today).data['campaigns']
            if c['campaign_id'] == daily_campaign.id
            for e in c['leaders']
        ]
        on_yesterday = [
            e['username']
            for c in global_leaderboard(yesterday).data['campaigns']
            if c['campaign_id'] == daily_campaign.id
            for e in c['leaders']
        ]

        assert 'glb_late_u1' not in on_today, "23:30 landed on the following day's board"
        assert 'glb_late_u1' in on_yesterday
    finally:
        reel.delete()
        user.delete()


def test_the_default_date_is_the_local_day(db, daily_campaign):
    """With no ?date, the board must be the day the subscriber is living in.

    Between midnight and 3am local this returned the previous date, because
    it came from a UTC clock.
    """
    local_today = timezone.localtime(timezone.now()).strftime('%Y-%m-%d')

    response = global_leaderboard(factory.get('/leaderboard/global/?period=daily'))

    assert response.status_code == 200, response.data
    assert (
        response.data.get('date') == local_today
    ), f'defaulted to {response.data.get("date")}, local today is {local_today}'
