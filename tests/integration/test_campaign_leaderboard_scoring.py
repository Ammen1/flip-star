"""
Campaign engagement counting, leaderboard scoring and ranking.

    score = likes x 1 + comments x 2 + shares x 5 + gifts x 10

Three defects these pin
-----------------------
Shares were never counted. Both the leaderboard endpoint and the scoring engine
carried ``total_shares = 0  # TODO: implement shares tracking``, so the share
weight multiplied zero -- a post could be shared any number of times and its
owner's score would not move. ``Reel.shares`` had been incremented by the share
endpoint the whole time.

Soft-deleted comments still scored. Comments were counted with a plain
``.count()``, which includes rows flagged ``is_deleted``: comment, collect two
points, delete the comment, keep the points.

Ranking was not deterministic. Participants were sorted on score alone over a
queryset with no ordering, so two people on equal points could swap places
between two requests -- on the board that decides who gets rewarded.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from api.models import Comment, Reel, Vote
from api.models.campaign import Campaign
from api.models.campaign_extended import CampaignScoringConfig, PostScore
from api.models.gift import Gift, GiftTransaction
from api.services.scoring.leaderboard import (
    COMMENT_WEIGHT,
    GIFT_WEIGHT,
    LIKE_WEIGHT,
    SHARE_WEIGHT,
    campaign_participant_totals,
    compute_score,
    rank,
    reel_engagement,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_campaign(title='Test Campaign', **kwargs):
    from django.utils import timezone

    return Campaign.objects.create(
        title=title,
        description='x',
        prize_title='Prize',
        prize_description='A prize',
        campaign_type='daily',
        start_date=timezone.now(),
        entry_deadline=timezone.now() + timedelta(days=7),
        **kwargs,
    )


@pytest.fixture
def campaign(db):
    return make_campaign()


@pytest.fixture
def alice():
    return User.objects.create_user(username='alice', password='123456')


@pytest.fixture
def bob():
    return User.objects.create_user(username='bob', password='123456')


@pytest.fixture
def fan():
    return User.objects.create_user(username='fan', password='123456')


def campaign_post(user, campaign, **kwargs):
    """A post entered into a campaign, approved for scoring."""
    reel = Reel.objects.create(user=user, caption='entry', media='reels/x.mp4', **kwargs)
    PostScore.objects.create(reel=reel, campaign=campaign, user=user, moderation_status='approved')
    return reel


def engage(reel, *, likes=0, comments=0, shares=0, gifts=0, deleted_comments=0):
    """Create real engagement rows, the way the app would."""
    for i in range(likes):
        Vote.objects.create(
            user=User.objects.create_user(username=f'liker{reel.id}_{i}', password='x'), reel=reel
        )
    for i in range(comments):
        Comment.objects.create(
            user=User.objects.create_user(username=f'cmt{reel.id}_{i}', password='x'),
            reel=reel,
            text='nice',
        )
    for i in range(deleted_comments):
        Comment.objects.create(
            user=User.objects.create_user(username=f'del{reel.id}_{i}', password='x'),
            reel=reel,
            text='gone',
            is_deleted=True,
        )
    if shares:
        Reel.objects.filter(pk=reel.pk).update(shares=shares)
        reel.refresh_from_db(fields=['shares'])
    if gifts:
        gift = Gift.objects.create(name=f'rose{reel.id}', coin_value=5)
        for i in range(gifts):
            GiftTransaction.objects.create(
                sender=User.objects.create_user(username=f'gifter{reel.id}_{i}', password='x'),
                recipient=reel.user,
                gift=gift,
                reel=reel,
                quantity=1,
                total_coins=5,
            )
    return reel


def totals_for(campaign):
    return campaign_participant_totals(
        campaign, PostScore.objects.filter(campaign=campaign, moderation_status='approved')
    )


# ---------------------------------------------------------------------------
# The weights (spec 2)
# ---------------------------------------------------------------------------


def test_the_weights_are_the_documented_ones():
    assert (LIKE_WEIGHT, COMMENT_WEIGHT, SHARE_WEIGHT, GIFT_WEIGHT) == (1, 2, 5, 10)


def test_a_like_is_worth_one_point(campaign, alice):
    engage(campaign_post(alice, campaign), likes=1)

    assert totals_for(campaign)[0]['leaderboard_score'] == 1


def test_a_comment_is_worth_two_points(campaign, alice):
    engage(campaign_post(alice, campaign), comments=1)

    assert totals_for(campaign)[0]['leaderboard_score'] == 2


def test_a_share_is_worth_five_points(campaign, alice):
    """
    The regression that mattered most.

    Shares were hardcoded to zero at both call sites, so this was 0 no matter
    how the campaign was configured.
    """
    engage(campaign_post(alice, campaign), shares=1)

    assert totals_for(campaign)[0]['leaderboard_score'] == 5


def test_a_gift_is_worth_ten_points(campaign, alice):
    engage(campaign_post(alice, campaign), gifts=1)

    assert totals_for(campaign)[0]['leaderboard_score'] == 10


def test_the_worked_example_from_the_specification(campaign, alice):
    """100 likes, 20 comments, 4 shares, 3 gifts -> 190."""
    engage(campaign_post(alice, campaign), likes=100, comments=20, shares=4, gifts=3)

    row = totals_for(campaign)[0]

    assert (row['likes'], row['comments'], row['shares'], row['gifts']) == (100, 20, 4, 3)
    assert row['leaderboard_score'] == 190


def test_the_score_always_equals_the_formula(campaign, alice):
    """Stated independently of any single arithmetic example."""
    engage(campaign_post(alice, campaign), likes=7, comments=3, shares=2, gifts=1)

    row = totals_for(campaign)[0]
    expected = row['likes'] * 1 + row['comments'] * 2 + row['shares'] * 5 + row['gifts'] * 10

    assert row['leaderboard_score'] == expected


def test_engagement_across_several_posts_accumulates(campaign, alice):
    engage(campaign_post(alice, campaign), likes=10, shares=1)
    engage(campaign_post(alice, campaign), comments=5, gifts=2)

    row = totals_for(campaign)[0]

    assert (row['likes'], row['comments'], row['shares'], row['gifts']) == (10, 5, 1, 2)
    assert row['leaderboard_score'] == 10 + 10 + 5 + 20


# ---------------------------------------------------------------------------
# What must not count (spec 3)
# ---------------------------------------------------------------------------


def test_an_unlike_removes_its_point(campaign, alice, fan):
    reel = campaign_post(alice, campaign)
    vote = Vote.objects.create(user=fan, reel=reel)
    assert totals_for(campaign)[0]['leaderboard_score'] == 1

    vote.delete()

    assert totals_for(campaign)[0]['leaderboard_score'] == 0


def test_a_deleted_comment_stops_counting(campaign, alice, fan):
    """
    Comment, collect two points, delete the comment, keep the points.

    That was the behaviour: the count included soft-deleted rows.
    """
    reel = campaign_post(alice, campaign)
    comment = Comment.objects.create(user=fan, reel=reel, text='hi')
    assert totals_for(campaign)[0]['leaderboard_score'] == 2

    comment.is_deleted = True
    comment.save(update_fields=['is_deleted'])

    assert totals_for(campaign)[0]['leaderboard_score'] == 0


def test_engagement_on_an_ordinary_post_does_not_count(campaign, alice, fan):
    """
    A post outside the campaign has no PostScore row, so it cannot reach the
    board however much engagement it collects.
    """
    campaign_post(alice, campaign)
    ordinary = Reel.objects.create(user=alice, caption='not an entry', media='reels/o.mp4')
    engage(ordinary, likes=50, comments=20, shares=9, gifts=5)

    assert totals_for(campaign)[0]['leaderboard_score'] == 0


def test_a_post_awaiting_moderation_does_not_count(campaign, alice):
    reel = Reel.objects.create(user=alice, caption='pending', media='reels/p.mp4')
    PostScore.objects.create(reel=reel, campaign=campaign, user=alice, moderation_status='pending')
    engage(reel, likes=30)

    assert totals_for(campaign) == []


def test_another_campaigns_engagement_does_not_leak_in(campaign, alice):
    other = make_campaign('Other')
    engage(campaign_post(alice, campaign), likes=3)
    engage(campaign_post(alice, other), likes=100)

    assert totals_for(campaign)[0]['leaderboard_score'] == 3


# ---------------------------------------------------------------------------
# Ranking and tie-breaking (spec 6, 7)
# ---------------------------------------------------------------------------


def test_participants_are_ordered_by_score(campaign, alice, bob):
    engage(campaign_post(alice, campaign), likes=10)
    engage(campaign_post(bob, campaign), likes=50)

    rows = totals_for(campaign)

    assert [r['user_id'] for r in rows] == [bob.id, alice.id]
    assert [r['rank'] for r in rows] == [1, 2]


def test_a_tie_is_broken_by_total_engagement(campaign, alice, bob):
    """
    Two participants reaching the same score by different routes.

    The specification illustrates this with A = 50/10/4/2 and B = 40/20/5/1,
    calling both 100 points -- but under the stated weights those are 110 and
    115, so they are not actually a tie and cannot exercise the tie-break. The
    numbers here do tie, on the formula as specified.

      alice  50x1 + 10x2 + 4x5 + 2x10 = 110, from 66 separate actions
      bob   100x1 +  5x2 + 0x5 + 0x10 = 110, from 105 separate actions

    More engagement for the same score places higher.
    """
    engage(campaign_post(alice, campaign), likes=50, comments=10, shares=4, gifts=2)
    engage(campaign_post(bob, campaign), likes=100, comments=5)

    rows = totals_for(campaign)

    assert rows[0]['leaderboard_score'] == rows[1]['leaderboard_score'] == 110
    assert rows[0]['user_id'] == bob.id, 'more engagement should win the tie'
    assert [r['rank'] for r in rows] == [1, 2]


def test_ranking_is_deterministic_across_repeated_calls(campaign, alice, bob):
    """
    Ranking decides who gets rewarded, so it must not depend on row order.

    The old implementation sorted on score alone over an unordered queryset.
    """
    engage(campaign_post(alice, campaign), likes=10)
    engage(campaign_post(bob, campaign), likes=10)

    orders = {tuple(r['user_id'] for r in totals_for(campaign)) for _ in range(5)}

    assert len(orders) == 1, f'ranking varied between calls: {orders}'


def test_a_perfect_tie_falls_back_to_user_id_not_chance():
    rows = [
        {'user_id': 9, 'likes': 1, 'comments': 0, 'shares': 0, 'gifts': 0, 'leaderboard_score': 1},
        {'user_id': 2, 'likes': 1, 'comments': 0, 'shares': 0, 'gifts': 0, 'leaderboard_score': 1},
    ]

    assert [r['user_id'] for r in rank(rows)] == [2, 9]


def test_more_engagement_outranks_fewer_at_the_same_score():
    rows = [
        # 10 points from one gift
        {'user_id': 1, 'likes': 0, 'comments': 0, 'shares': 0, 'gifts': 1, 'leaderboard_score': 10},
        # 10 points from ten likes
        {
            'user_id': 2,
            'likes': 10,
            'comments': 0,
            'shares': 0,
            'gifts': 0,
            'leaderboard_score': 10,
        },
    ]

    assert [r['user_id'] for r in rank(rows)] == [2, 1]


# ---------------------------------------------------------------------------
# Configurable weights
# ---------------------------------------------------------------------------


def test_a_campaign_may_configure_its_own_weights(campaign, alice):
    CampaignScoringConfig.objects.update_or_create(
        campaign=campaign, defaults={'daily_likes_weight': 3}
    )
    engage(campaign_post(alice, campaign), likes=4)

    # The campaign's own weight is used, not the module default.
    assert totals_for(campaign)[0]['leaderboard_score'] == 12


def test_compute_score_is_pure_arithmetic():
    counts = {'likes': 100, 'comments': 20, 'shares': 4, 'gifts': 3}

    assert compute_score(counts) == 190


def test_the_shipped_defaults_match_the_specification(campaign):
    config, _ = CampaignScoringConfig.objects.get_or_create(campaign=campaign)

    assert float(config.daily_likes_weight) == 1
    assert float(config.daily_comments_weight) == 2
    assert float(config.daily_shares_weight) == 5
    assert float(config.daily_gifts_weight) == 10


# ---------------------------------------------------------------------------
# The API contract (spec 8)
# ---------------------------------------------------------------------------


def test_the_share_endpoint_returns_the_canonical_block(campaign, alice, fan):
    reel = engage(campaign_post(alice, campaign), likes=2, comments=1)
    client = APIClient()
    client.force_authenticate(user=fan)

    response = client.post(f'/api/v1/reels/{reel.id}/share/')

    assert response.status_code == 200, response.data
    for field in ('likes', 'comments', 'shares', 'gifts', 'leaderboard_score', 'coins_charged'):
        assert field in response.data, f'{field} missing from the share response'
    assert response.data['shares'] == 1


def test_the_share_response_score_matches_the_formula(campaign, alice, fan):
    reel = engage(campaign_post(alice, campaign), likes=3, comments=2, gifts=1)
    client = APIClient()
    client.force_authenticate(user=fan)

    data = client.post(f'/api/v1/reels/{reel.id}/share/').data

    expected = data['likes'] * 1 + data['comments'] * 2 + data['shares'] * 5 + data['gifts'] * 10
    assert data['leaderboard_score'] == expected


def test_the_legacy_field_names_still_work(campaign, alice, fan):
    """
    Backward compatibility.

    Existing clients read `shares` and `votes`; both keep their meaning.
    """
    reel = engage(campaign_post(alice, campaign), likes=4)
    client = APIClient()
    client.force_authenticate(user=fan)

    data = client.post(f'/api/v1/reels/{reel.id}/share/').data

    assert data['votes'] == data['likes'] == 4


def test_the_share_count_reaches_the_leaderboard(campaign, alice, fan):
    """
    End to end, the path that was broken.

    Share the post through the API, then read the board: the five points must
    be there. Previously the endpoint incremented Reel.shares and the
    leaderboard ignored it.
    """
    reel = campaign_post(alice, campaign)
    client = APIClient()
    client.force_authenticate(user=fan)

    client.post(f'/api/v1/reels/{reel.id}/share/')

    assert totals_for(campaign)[0]['shares'] == 1
    assert totals_for(campaign)[0]['leaderboard_score'] == 5


def test_the_leaderboard_endpoint_reports_canonical_fields(campaign, alice):
    engage(campaign_post(alice, campaign), likes=100, comments=20, shares=4, gifts=3)
    admin = User.objects.create_superuser(username='admin', password='x')
    client = APIClient()
    client.force_authenticate(user=admin)

    response = client.get(f'/api/v1/campaigns/{campaign.id}/leaderboard/')

    assert response.status_code == 200, response.data
    entry = response.data['entries'][0]
    assert entry['likes'] == 100
    assert entry['comments'] == 20
    assert entry['shares'] == 4
    assert entry['gifts'] == 3
    assert entry['leaderboard_score'] == 190
    assert entry['rank'] == 1
    # The names the existing UI reads, carrying the same numbers.
    assert entry['likes_count'] == 100
    assert entry['total_score'] == 190


# ---------------------------------------------------------------------------
# Per-post counts
# ---------------------------------------------------------------------------


def test_reel_engagement_reads_the_database_not_the_counter(campaign, alice, fan):
    """
    Reel.votes is a denormalised counter maintained by several code paths and
    it drifts. The score is built from the rows instead.
    """
    reel = campaign_post(alice, campaign)
    Vote.objects.create(user=fan, reel=reel)
    Reel.objects.filter(pk=reel.pk).update(votes=999)
    reel.refresh_from_db()

    assert reel_engagement(reel)['likes'] == 1


def test_duplicate_likes_cannot_inflate_a_score(campaign, alice, fan):
    """One user, one like -- enforced by the database, verified here."""
    from django.db import IntegrityError, transaction

    reel = campaign_post(alice, campaign)
    Vote.objects.create(user=fan, reel=reel)

    try:
        with transaction.atomic():
            Vote.objects.create(user=fan, reel=reel)
    except IntegrityError:
        pass

    assert totals_for(campaign)[0]['likes'] == 1
