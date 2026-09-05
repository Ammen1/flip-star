"""
A paid boost has to actually change what people see.

What was wrong
--------------
The boost machinery was written but never connected to anything:

  Reel.is_boosted        set when a campaign starts, read by no feed query
  BoostConfig.injection_ratio  configured ("1 boost per X organic posts"),
                         referenced nowhere outside its own model
  /boost/eligible/       served at api/urls.py:1254, called by no client

So a user spent coins and received no additional visibility whatsoever. That
is the worst shape a payment bug can take: the money moves, the records look
correct, and the thing bought silently does not exist.

Both trending views now rank an actively boosted post first. The condition is
the same one get_eligible_boosts already used -- status, an end time still in
the future, and budget remaining -- so "boosted" cannot mean two different
things depending on which code path asks.

Deliberately NOT changed: ranking within each group. An unboosted feed comes
back in exactly the order it did before, so this cannot be blamed for a
reordering nobody asked for.
"""

import fakeredis
import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from api.models import Reel
from api.models.boost import BoostCampaign
from common.security.e2e_encryption import generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.django_db


@pytest.fixture
def server_keys(db):
    """get_trending_reels carries @encrypted_endpoint, so the server needs keys.

    The decorator seals the RESPONSE, so even a GET with no body is refused
    without X-Client-Public-Key -- 400 decryption_failed before the view runs.
    """
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def client_keys():
    return generate_keypair()


@pytest.fixture
def author():
    return User.objects.create_user(username='boost_author', password='x')


@pytest.fixture
def viewer():
    return User.objects.create_user(username='boost_viewer', password='x')


def make_reel(author, votes=0, caption='post'):
    reel = Reel.objects.create(user=author, caption=caption)
    if votes:
        Reel.objects.filter(pk=reel.pk).update(votes=votes)
        reel.refresh_from_db()
    return reel


def boost(reel, *, status='active', hours=24, coins_remaining=100):
    """A campaign as the boost flow creates one.

    start_time is auto_now_add, so it is never passed; the other required
    fields are given plausible values rather than left to defaults they do
    not have.
    """
    return BoostCampaign.objects.create(
        reel=reel,
        user=reel.user,
        status=status,
        duration_hours=hours,
        coins_spent=100,
        coins_remaining=coins_remaining,
        end_time=timezone.now() + timezone.timedelta(hours=hours),
        expected_impressions=1000,
        hourly_budget=100 / hours,
    )


def trending_ids(user, client_keys, limit=20):
    """The explorer trending feed, which is what the Trending tab calls.

    Assertions read response.data rather than the rendered body: DRF holds the
    plain payload until render time, so the encryption wrapper is transparent
    here.
    """
    from rest_framework.test import APIRequestFactory, force_authenticate

    from api.views.core import get_trending_reels

    client_public_key, _ = client_keys
    request = APIRequestFactory().get(
        f'/explorer/trending/?limit={limit}',
        HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
    )
    force_authenticate(request, user=user)
    response = get_trending_reels(request)
    assert response.status_code == 200, response.data
    rows = response.data if isinstance(response.data, list) else response.data.get('results', [])
    return [row['id'] for row in rows]


# ---------------------------------------------------------------------------
# A boost changes placement
# ---------------------------------------------------------------------------


def test_a_boosted_post_outranks_a_more_popular_one(author, viewer, server_keys, client_keys):
    """
    The point of paying.

    Without this the boosted post sits below anything with more votes, which
    is exactly where it was before the user paid.
    """
    popular = make_reel(author, votes=500, caption='organic favourite')
    boosted = make_reel(author, votes=1, caption='paid for reach')
    boost(boosted)

    ids = trending_ids(viewer, client_keys)

    assert ids.index(boosted.id) < ids.index(popular.id)


def test_an_unboosted_feed_keeps_its_existing_order(author, viewer, server_keys, client_keys):
    """
    The regression guard.

    Ranking within each group is untouched, so a feed with no boosts must come
    back exactly as it did before.
    """
    high = make_reel(author, votes=100)
    mid = make_reel(author, votes=50)
    low = make_reel(author, votes=1)

    ids = trending_ids(viewer, client_keys)

    assert ids.index(high.id) < ids.index(mid.id) < ids.index(low.id)


def test_boosted_posts_are_still_ordered_among_themselves(author, viewer, server_keys, client_keys):
    """Boosting does not flatten ranking -- it lifts a whole group."""
    quiet = make_reel(author, votes=2)
    loud = make_reel(author, votes=200)
    boost(quiet)
    boost(loud)

    ids = trending_ids(viewer, client_keys)

    assert ids.index(loud.id) < ids.index(quiet.id)


# ---------------------------------------------------------------------------
# What does not count as boosted
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('label', 'kwargs'),
    [
        ('paused', {'status': 'paused'}),
        ('completed', {'status': 'completed'}),
        ('cancelled', {'status': 'cancelled'}),
    ],
)
def test_a_non_active_campaign_gives_no_lift(
    author, viewer, server_keys, client_keys, label, kwargs
):
    popular = make_reel(author, votes=500)
    inactive = make_reel(author, votes=1)
    boost(inactive, **kwargs)

    ids = trending_ids(viewer, client_keys)

    assert ids.index(popular.id) < ids.index(inactive.id), f'{label} campaign still lifted'


def test_an_expired_campaign_gives_no_lift(author, viewer, server_keys, client_keys):
    """
    Paying for 24 hours buys 24 hours.

    end_time is checked at query time rather than relying on a background job
    to flip a flag, so a boost stops working the moment it expires even if
    nothing has swept it yet.
    """
    popular = make_reel(author, votes=500)
    expired = make_reel(author, votes=1)
    campaign = boost(expired)
    BoostCampaign.objects.filter(pk=campaign.pk).update(
        end_time=timezone.now() - timezone.timedelta(hours=1)
    )

    ids = trending_ids(viewer, client_keys)

    assert ids.index(popular.id) < ids.index(expired.id)


def test_a_campaign_with_no_budget_left_gives_no_lift(author, viewer, server_keys, client_keys):
    """Spent budget is spent, whatever the status field says."""
    popular = make_reel(author, votes=500)
    broke_post = make_reel(author, votes=1)
    boost(broke_post, coins_remaining=0)

    ids = trending_ids(viewer, client_keys)

    assert ids.index(popular.id) < ids.index(broke_post.id)


# ---------------------------------------------------------------------------
# Both endpoints agree
# ---------------------------------------------------------------------------


def test_the_other_trending_endpoint_is_also_boost_aware():
    """
    /reels/trending/ and /explorer/trending/ serve the same idea to different
    clients. If only one were boost-aware, a boost would work or not depending
    on whether the caller was web or mobile.
    """
    from pathlib import Path

    import api.views.core as core_module
    import api.views.reels as reels_module

    for module in (core_module, reels_module):
        src = Path(module.__file__).read_text(encoding='utf-8')
        assert 'has_active_boost' in src, f'{module.__name__} ignores boosts'
        assert "order_by('-has_active_boost'" in src, f'{module.__name__} annotates but never sorts'


def test_both_endpoints_use_the_same_definition_of_active():
    """
    The condition is duplicated in three places now -- get_eligible_boosts and
    the two feeds -- so this pins them together until there is a reason to
    extract it.
    """
    from pathlib import Path

    import api.views.boost as boost_module
    import api.views.core as core_module
    import api.views.reels as reels_module

    for module in (boost_module, core_module, reels_module):
        src = Path(module.__file__).read_text(encoding='utf-8')
        assert "status='active'" in src
        assert 'coins_remaining__gt=0' in src


# ---------------------------------------------------------------------------
# Expiry sweep
# ---------------------------------------------------------------------------


def test_a_finished_campaign_is_marked_completed(author):
    """
    Nothing retired boost campaigns before this.

    Staging holds one that ended fourteen hours ago, still status='active'.
    Trending is immune because it re-checks end_time, but anything filtering
    on status alone is not.
    """
    from api.tasks.boost import expire_boost_campaigns

    reel = make_reel(author)
    campaign = boost(reel)
    BoostCampaign.objects.filter(pk=campaign.pk).update(
        end_time=timezone.now() - timezone.timedelta(hours=1)
    )

    expire_boost_campaigns()

    campaign.refresh_from_db()
    assert campaign.status == 'completed'


def test_a_running_campaign_is_left_alone(author):
    from api.tasks.boost import expire_boost_campaigns

    reel = make_reel(author)
    campaign = boost(reel, hours=24)

    expire_boost_campaigns()

    campaign.refresh_from_db()
    assert campaign.status == 'active'


def test_the_sweep_is_idempotent(author):
    """Re-running immediately must be a no-op, not a second completion."""
    from api.tasks.boost import expire_boost_campaigns

    reel = make_reel(author)
    campaign = boost(reel)
    BoostCampaign.objects.filter(pk=campaign.pk).update(
        end_time=timezone.now() - timezone.timedelta(hours=1)
    )

    first = expire_boost_campaigns()
    second = expire_boost_campaigns()

    assert 'Completed 1' in first
    assert 'Completed 0' in second


def test_unspent_coins_are_reported_not_silently_taken(author):
    """
    Refunding is a commercial decision, not this task's to make.

    The amount is surfaced so it can be reconciled deliberately; moving a
    customer's coins on our own initiative is the one thing this must not do.
    """
    from api.tasks.boost import expire_boost_campaigns

    reel = make_reel(author)
    campaign = boost(reel, coins_remaining=442)
    BoostCampaign.objects.filter(pk=campaign.pk).update(
        end_time=timezone.now() - timezone.timedelta(hours=1)
    )

    result = expire_boost_campaigns()

    campaign.refresh_from_db()
    assert '442' in result
    assert campaign.coins_remaining == 442, 'the balance was altered'


def test_the_post_flag_is_cleared(author):
    """A finished boost must not leave the post looking boosted."""
    from api.tasks.boost import expire_boost_campaigns

    reel = make_reel(author)
    campaign = boost(reel)
    Reel.objects.filter(pk=reel.pk).update(is_boosted=True)
    BoostCampaign.objects.filter(pk=campaign.pk).update(
        end_time=timezone.now() - timezone.timedelta(hours=1)
    )

    expire_boost_campaigns()

    reel.refresh_from_db()
    assert reel.is_boosted is False


def test_a_newer_live_boost_survives_an_older_one_expiring(author):
    """
    A post can carry several campaigns over its life. Clearing the flag
    unconditionally when an old one expires would switch off a boost the user
    is still paying for.
    """
    from api.tasks.boost import expire_boost_campaigns

    reel = make_reel(author)
    old = boost(reel)
    boost(reel, hours=24)  # still running
    Reel.objects.filter(pk=reel.pk).update(is_boosted=True)
    BoostCampaign.objects.filter(pk=old.pk).update(
        end_time=timezone.now() - timezone.timedelta(hours=1)
    )

    expire_boost_campaigns()

    reel.refresh_from_db()
    assert reel.is_boosted is True, 'a live boost was switched off'
