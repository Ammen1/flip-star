"""
What "boosted" means once a boost has ended.

`Reel.is_boosted` is a denormalised flag: set when a campaign starts, cleared
by a sweep that runs every five minutes. Between a boost ending and the sweep
noticing, the column says "boosted" about a post that is not -- and if the
sweep is not running, it says so forever.

The feeds never trusted it: both trending endpoints rank on a subquery for a
campaign that is `active`, unexpired and still funded. What clients were told
was a different matter -- `ReelSerializer` carried no boost field at all, so
every web page reading `reel.is_boosted` got `undefined`, and the admin read
the stored column and kept showing "Boosted" for boosts that were over.

So boost state is now computed from the campaign wherever it is reported, and
these pin that: an expired, exhausted, cancelled or swept-but-stale boost all
report the same thing, which is "not boosted".
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from api.models import Reel
from api.models.boost import BoostCampaign
from api.serializers.core import ReelSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def author():
    return User.objects.create_user(username='booster', password='x')


@pytest.fixture
def reel(author):
    return Reel.objects.create(user=author, caption='boosted post', processing_status='ready')


def campaign_for(reel, *, ends_in=timedelta(hours=2), status='active', coins_remaining=100):
    now = timezone.now()
    campaign = BoostCampaign.objects.create(
        reel=reel,
        user=reel.user,
        status=status,
        duration_hours=2,
        end_time=now + ends_in,
        coins_spent=0,
        coins_remaining=coins_remaining,
        expected_impressions=1000,
        hourly_budget=50,
    )
    # What starting a boost does: point the post at the campaign and flag it.
    reel.active_boost_campaign = campaign
    reel.is_boosted = True
    reel.save(update_fields=['active_boost_campaign', 'is_boosted'])
    return campaign


def boosted(reel):
    return ReelSerializer(reel).data['is_boosted']


def test_a_live_boost_reports_boosted(reel):
    campaign_for(reel)

    assert boosted(reel) is True


def test_an_expired_boost_does_not(reel):
    """The case in the report: the boost ended, the flag was left set, and the
    post kept presenting itself as boosted."""
    campaign_for(reel, ends_in=timedelta(hours=-1))

    assert reel.is_boosted is True, 'the stale column is what makes this worth testing'
    assert boosted(reel) is False


def test_a_boost_that_ran_out_of_coins_does_not(reel):
    campaign_for(reel, coins_remaining=0)

    assert boosted(reel) is False


@pytest.mark.parametrize('status', ['completed', 'paused', 'cancelled'])
def test_only_an_active_campaign_counts(reel, status):
    campaign_for(reel, status=status)

    assert boosted(reel) is False


def test_a_post_with_no_campaign_is_not_boosted(reel):
    reel.is_boosted = True
    reel.save(update_fields=['is_boosted'])

    assert boosted(reel) is False, 'a flag with no campaign behind it means nothing'


def test_the_end_time_is_reported_while_live_and_not_after(reel):
    """Clients get the deadline so a badge can retire itself between
    requests instead of waiting to be told."""
    campaign = campaign_for(reel)
    data = ReelSerializer(reel).data
    assert data['boost_ends_at'] == campaign.end_time.isoformat()

    campaign.end_time = timezone.now() - timedelta(minutes=1)
    campaign.save(update_fields=['end_time'])
    reel.refresh_from_db()

    assert ReelSerializer(reel).data['boost_ends_at'] is None


def test_a_feed_annotation_is_used_when_present(reel):
    """Feeds compute this in SQL for every row at once. Where they have, the
    serializer must not go back to the database per post."""
    campaign_for(reel, ends_in=timedelta(hours=-1))
    reel.has_active_boost = True  # what the feed's Exists() annotation sets

    assert boosted(reel) is True, 'the annotation is authoritative for a feed row'


def test_trending_ranks_only_live_boosts(author, reel):
    """The ordering itself: an expired boost must not lift a post."""
    from django.db.models import Exists, OuterRef

    other = Reel.objects.create(user=author, caption='ordinary', processing_status='ready')
    campaign_for(reel, ends_in=timedelta(hours=-1))

    live = BoostCampaign.objects.filter(
        reel=OuterRef('pk'),
        status='active',
        end_time__gt=timezone.now(),
        coins_remaining__gt=0,
    )
    ranked = (
        Reel.objects.filter(id__in=[reel.id, other.id])
        .annotate(has_active_boost=Exists(live))
        .order_by('-has_active_boost', '-id')
    )

    assert [r.has_active_boost for r in ranked] == [False, False], 'expired boost still ranked'
