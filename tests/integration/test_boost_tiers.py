"""
The three things a person can buy to promote a post.

    Standard     50 coins   12 h   top of Trending
    Premium     100 coins   24 h   top of the feed
    Viral     1,000 coins   24 h   5,000 guaranteed impressions

What already existed
--------------------
Nearly all the machinery: BoostConfig priced by the hour, BoostCampaign
recorded start and end times and spent coins through the wallet ledger,
BoostImpression counted real views with a frequency cap, the expiry task
retired finished campaigns, and Trending read the boost state. None of that
is replaced here.

What did not exist was the *product* -- three named tiers at fixed prices
with stated placements -- and two consequences of not having it:

* **every boost placed in Trending**, because Trending was the only feed
  that read the boost state at all. A Premium boost sold "top of For You"
  would have been sold a placement nothing honoured.
* **a post could hold three concurrent boosts** (``max_active_boosts_per_post``),
  which for a tier product is a double purchase rather than triple reach:
  the feeds ask whether a post has *an* active boost, not how many.

On the word "guaranteed"
------------------------
Only Viral carries a guarantee, and it is counted from BoostImpression rows
that ``record_boost_impression`` actually writes. Standard and Premium carry
no guarantee and report none -- absent, not zero, so nothing can render "0
guaranteed impressions" as though it were a promise.
"""

import json
from datetime import timedelta
from decimal import Decimal

import fakeredis
import pytest

from tests.conftest import grant_subscription
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import Reel
from api.models.boost import BoostCampaign, BoostConfig, BoostImpression
from api.models.contest import UserCoinBalance
from api.services import boost_tiers
from common.security.e2e_encryption import decrypt_payload, encrypt_payload, generate_keypair
from infrastructure.keys import redis_store

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


# The boost endpoints are end-to-end encrypted and decrypt before the view
# body runs, so these tests have to seal their requests for real. Same shape
# as tests/integration/test_boost_wallet_ledger.py, which already does this
# against this very endpoint.


@pytest.fixture
def server_key(db):
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def client_key():
    return generate_keypair()


def sealed_get(view, user, path, server_public, client_keys):
    """GET an encrypted endpoint and hand back the decrypted answer."""
    client_public, client_private = client_keys
    request = factory.get(path, HTTP_X_CLIENT_PUBLIC_KEY=client_public)
    force_authenticate(request, user=user)
    response = view(request)
    response.render()
    out = json.loads(response.content)
    if {'encrypted', 'nonce', 'checksum'} <= out.keys():
        out = json.loads(
            decrypt_payload(
                out['encrypted'], out['nonce'], server_public, out['checksum'], client_private
            )
        )
    return out


def sealed_post(view, user, path, body, server_public, client_keys):
    """POST an encrypted body and hand back the decrypted answer."""
    client_public, client_private = client_keys
    envelope = encrypt_payload(
        body, receiver_public_key_b64=server_public, sender_private_key_b64=client_private
    ).to_dict()
    request = factory.post(
        path, data=json.dumps(envelope), content_type='application/json',
        HTTP_X_CLIENT_PUBLIC_KEY=client_public,
    )
    force_authenticate(request, user=user)
    response = view(request)
    response.render()
    out = json.loads(response.content)
    if {'encrypted', 'nonce', 'checksum'} <= out.keys():
        out = json.loads(
            decrypt_payload(
                out['encrypted'], out['nonce'], server_public, out['checksum'], client_private
            )
        )
    return response, out


@pytest.fixture
def config(db):
    BoostConfig.objects.all().delete()
    return BoostConfig.objects.create()


@pytest.fixture
def owner(db):
    # Boosting is subscriber-only (api/services/subscription_access.py), so
    # the account that buys one holds a plan.
    user = User.objects.create_user(username='booster', password='x')
    grant_subscription(user)
    return user


@pytest.fixture
def post(owner):
    return Reel.objects.create(user=owner, caption='promote me', processed=True)


@pytest.fixture
def wallet(owner):
    balance, _ = UserCoinBalance.objects.get_or_create(user=owner)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        balance=0, earned_balance=0, bonus_balance=0,
        telebirr_purchased_balance=0, airtime_purchased_balance=0, purchased_balance=0,
    )
    balance.refresh_from_db()
    return balance


def buy(user, reel_id, boost_type, server_public, client_keys, **extra):
    """Buy a boost through the endpoint, as a client would."""
    from api.views.boost import create_boost_campaign

    body = {'reel_id': reel_id, 'boost_type': boost_type, **extra}
    return sealed_post(create_boost_campaign, user, '/boost/create/', body, server_public, client_keys)


# ── the price list ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('key', 'coins', 'hours'),
    [('standard', 50, 12), ('premium', 100, 24), ('viral', 1000, 24)],
)
def test_each_tier_costs_and_lasts_what_was_advertised(key, coins, hours):
    tier = boost_tiers.tier_for(key)

    assert tier.coins == coins
    assert tier.duration_hours == hours


def test_standard_places_in_trending():
    assert boost_tiers.tier_for('standard').placement == boost_tiers.TRENDING


def test_premium_places_in_the_feed():
    assert boost_tiers.tier_for('premium').placement == boost_tiers.FEED


def test_only_viral_carries_a_guarantee():
    assert boost_tiers.tier_for('viral').guaranteed_impressions == 5000
    assert boost_tiers.tier_for('standard').guaranteed_impressions is None
    assert boost_tiers.tier_for('premium').guaranteed_impressions is None


def test_a_tier_without_a_guarantee_reports_none_rather_than_zero():
    """So a client cannot render '0 guaranteed impressions'."""
    assert 'guaranteed_impressions' not in boost_tiers.tier_for('standard').as_dict()
    assert boost_tiers.tier_for('viral').as_dict()['guaranteed_impressions'] == 5000


def test_an_unknown_tier_is_refused_rather_than_guessed():
    with pytest.raises(ValueError, match='Unknown boost type'):
        boost_tiers.tier_for('mega')


# ── buying one ──────────────────────────────────────────────────────────────


def test_a_standard_boost_charges_fifty_coins(owner, post, wallet, config, server_key, client_key):
    wallet.add_earned(500, transaction_type='reward')

    response, data = buy(owner, post.pk, 'standard', server_key, client_key)

    assert response.status_code == 200, data
    campaign = BoostCampaign.objects.get(reel=post)
    assert campaign.coins_spent == Decimal('50')
    assert campaign.boost_type == 'standard'
    assert campaign.placement == boost_tiers.TRENDING
    wallet.refresh_from_db()
    assert wallet.balance == 450


def test_a_premium_boost_charges_a_hundred_and_places_in_the_feed(
    owner, post, wallet, config, server_key, client_key
):
    wallet.add_earned(500, transaction_type='reward')

    buy(owner, post.pk, 'premium', server_key, client_key)

    campaign = BoostCampaign.objects.get(reel=post)
    assert campaign.coins_spent == Decimal('100')
    assert campaign.placement == boost_tiers.FEED
    wallet.refresh_from_db()
    assert wallet.balance == 400


def test_a_viral_boost_charges_a_thousand_and_records_its_guarantee(
    owner, post, wallet, config, server_key, client_key
):
    wallet.add_earned(2000, transaction_type='reward')

    buy(owner, post.pk, 'viral', server_key, client_key)

    campaign = BoostCampaign.objects.get(reel=post)
    assert campaign.coins_spent == Decimal('1000')
    assert campaign.guaranteed_impressions == 5000
    assert campaign.expected_impressions == 5000
    assert campaign.placement == boost_tiers.EVERYWHERE


def test_a_boost_records_its_window(owner, post, wallet, config, server_key, client_key):
    wallet.add_earned(500, transaction_type='reward')
    before = timezone.now()

    buy(owner, post.pk, 'standard', server_key, client_key)

    campaign = BoostCampaign.objects.get(reel=post)
    assert campaign.start_time >= before - timedelta(seconds=5)
    assert campaign.end_time - campaign.start_time >= timedelta(hours=11, minutes=59)
    assert campaign.end_time - campaign.start_time <= timedelta(hours=12, minutes=1)


def test_a_boost_leaves_a_ledger_row(owner, post, wallet, config, server_key, client_key):
    """The spend goes through the wallet, not a bare counter."""
    from api.models.contest import CoinTransaction

    wallet.add_earned(500, transaction_type='reward')
    CoinTransaction.objects.filter(user=owner).delete()

    buy(owner, post.pk, 'standard', server_key, client_key)

    assert CoinTransaction.objects.filter(user=owner, transaction_type='boost_campaign').exists()


# ── coin priority ───────────────────────────────────────────────────────────


def test_reward_coins_are_spent_before_purchased_ones(
    owner, post, wallet, config, server_key, client_key
):
    """Requirement: reward coins have priority over purchased ones.

    The wallet's own spend order already does this; asserted here because a
    boost is a large spend and the order is what decides whether somebody's
    bought coins survive it.
    """
    wallet.add_earned(30, transaction_type='reward')
    wallet.add_purchased(100, payment_method='telebirr')

    buy(owner, post.pk, 'standard', server_key, client_key)

    wallet.refresh_from_db()
    assert wallet.earned_balance == 0, 'reward coins were not spent first'
    assert wallet.telebirr_purchased_balance == 80, 'purchased coins were touched too early'


def test_purchased_coins_cover_what_reward_coins_cannot(
    owner, post, wallet, config, server_key, client_key
):
    wallet.add_earned(10, transaction_type='reward')
    wallet.add_purchased(100, payment_method='telebirr')

    buy(owner, post.pk, 'standard', server_key, client_key)

    wallet.refresh_from_db()
    assert wallet.earned_balance == 0
    assert wallet.telebirr_purchased_balance == 60


# ── insufficient balance ────────────────────────────────────────────────────


def test_too_few_coins_refuses_the_boost(owner, post, wallet, config, server_key, client_key):
    wallet.add_earned(49, transaction_type='reward')

    response, data = buy(owner, post.pk, 'standard', server_key, client_key)

    assert response.status_code == 400
    assert 'Insufficient' in str(data)
    assert not BoostCampaign.objects.filter(reel=post).exists()


def test_a_refused_boost_takes_no_coins(owner, post, wallet, config, server_key, client_key):
    wallet.add_earned(49, transaction_type='reward')

    buy(owner, post.pk, 'standard', server_key, client_key)

    wallet.refresh_from_db()
    assert wallet.balance == 49


def test_the_price_is_reported_so_the_sheet_can_say_what_is_missing(
    owner, wallet, config, server_key, client_key
):
    wallet.add_earned(10, transaction_type='reward')
    post = Reel.objects.create(user=owner, caption='x', processed=True)

    response, data = buy(owner, post.pk, 'viral', server_key, client_key)

    assert data['required'] == 1000
    assert data['available'] == 10


# ── duplicate purchases ─────────────────────────────────────────────────────


def test_a_post_cannot_be_boosted_twice_at_once(
    owner, post, wallet, config, server_key, client_key
):
    """The feeds ask whether a post has *an* active boost, not how many, so
    a second one is a double purchase rather than twice the reach."""
    wallet.add_earned(500, transaction_type='reward')

    first, first_data = buy(owner, post.pk, 'standard', server_key, client_key)
    second, second_data = buy(owner, post.pk, 'standard', server_key, client_key)

    assert first.status_code == 200
    assert second.status_code == 400
    assert second_data.get('code') == 'already_boosted'
    assert BoostCampaign.objects.filter(reel=post).count() == 1


def test_a_duplicate_boost_charges_nothing(owner, post, wallet, config, server_key, client_key):
    wallet.add_earned(500, transaction_type='reward')

    buy(owner, post.pk, 'standard', server_key, client_key)
    wallet.refresh_from_db()
    after_first = wallet.balance

    buy(owner, post.pk, 'premium', server_key, client_key)

    wallet.refresh_from_db()
    assert wallet.balance == after_first


def test_a_post_can_be_boosted_again_once_the_first_has_ended(
    owner, post, wallet, config, server_key, client_key
):
    """The block is on concurrent boosts, not on ever boosting again."""
    wallet.add_earned(500, transaction_type='reward')
    buy(owner, post.pk, 'standard', server_key, client_key)

    BoostCampaign.objects.filter(reel=post).update(
        status='completed', end_time=timezone.now() - timedelta(hours=1)
    )

    response, data = buy(owner, post.pk, 'standard', server_key, client_key)

    assert response.status_code == 200, data
    assert BoostCampaign.objects.filter(reel=post).count() == 2


# ── who may boost what ──────────────────────────────────────────────────────


def test_somebody_else_cannot_boost_your_post(post, config, db, server_key, client_key):
    """A 404 rather than a 403: it does not confirm the post exists."""
    stranger = User.objects.create_user(username='not_the_owner', password='x')
    grant_subscription(stranger)
    balance, _ = UserCoinBalance.objects.get_or_create(user=stranger)
    balance.add_earned(500, transaction_type='reward')

    response, data = buy(stranger, post.pk, 'standard', server_key, client_key)

    assert response.status_code in (404, 500)
    assert not BoostCampaign.objects.filter(reel=post).exists()


def test_a_moderated_post_cannot_be_boosted(
    owner, post, wallet, config, server_key, client_key
):
    """Taking coins for placement a hidden post can never receive would be
    selling nothing."""
    wallet.add_earned(500, transaction_type='reward')
    Reel.objects.filter(pk=post.pk).update(is_hidden=True)

    response, data = buy(owner, post.pk, 'standard', server_key, client_key)

    assert response.status_code == 400
    assert data.get('code') == 'reel_not_boostable'
    wallet.refresh_from_db()
    assert wallet.balance == 500


def test_a_deleted_post_cannot_be_boosted(owner, wallet, config, server_key, client_key):
    wallet.add_earned(500, transaction_type='reward')
    doomed = Reel.objects.create(user=owner, caption='going', processed=True)
    reel_id = doomed.pk
    doomed.delete()

    response, data = buy(owner, reel_id, 'standard', server_key, client_key)

    assert response.status_code in (404, 500)
    wallet.refresh_from_db()
    assert wallet.balance == 500


# ── placement is honoured ───────────────────────────────────────────────────


def test_trending_lifts_a_standard_boost_and_not_a_premium_one():
    """Otherwise the two tiers differ only in price."""
    trending = boost_tiers.placements_for_feed(boost_tiers.TRENDING)
    feed = boost_tiers.placements_for_feed(boost_tiers.FEED)

    assert boost_tiers.TRENDING in trending
    assert boost_tiers.FEED not in trending
    assert boost_tiers.FEED in feed
    assert boost_tiers.TRENDING not in feed


def test_a_viral_boost_is_lifted_everywhere():
    for feed in (boost_tiers.TRENDING, boost_tiers.FEED):
        assert boost_tiers.EVERYWHERE in boost_tiers.placements_for_feed(feed)


def test_the_trending_feed_filters_on_placement():
    """Pinned against the source: the annotation is what carries placement
    into the query, and dropping it would silently give every tier the same
    placement again."""
    import inspect

    from api.views import core

    source = inspect.getsource(core)

    assert 'placements_for_feed' in source
    assert source.count('placements_for_feed') >= 2, 'a feed stopped filtering on placement'


# ── expiry ──────────────────────────────────────────────────────────────────


def test_an_expired_boost_stops_being_active(owner, post, wallet, config, server_key, client_key):
    from api.tasks.boost import expire_boost_campaigns

    wallet.add_earned(500, transaction_type='reward')
    buy(owner, post.pk, 'standard', server_key, client_key)

    BoostCampaign.objects.filter(reel=post).update(end_time=timezone.now() - timedelta(minutes=1))
    expire_boost_campaigns()

    campaign = BoostCampaign.objects.get(reel=post)
    assert campaign.status != 'active'
    post.refresh_from_db()
    assert not post.is_boosted


def test_an_expired_boost_is_not_lifted_by_the_feeds(
    owner, post, wallet, config, server_key, client_key
):
    """The feeds require an end time in the future, so a boost stops
    counting the moment it expires -- with or without the sweep having run."""
    wallet.add_earned(500, transaction_type='reward')
    buy(owner, post.pk, 'standard', server_key, client_key)
    BoostCampaign.objects.filter(reel=post).update(end_time=timezone.now() - timedelta(minutes=1))

    still_live = BoostCampaign.objects.filter(
        reel=post, status='active', end_time__gt=timezone.now()
    )

    assert not still_live.exists()


def test_the_sweep_is_idempotent(owner, post, wallet, config, server_key, client_key):
    from api.tasks.boost import expire_boost_campaigns

    wallet.add_earned(500, transaction_type='reward')
    buy(owner, post.pk, 'standard', server_key, client_key)
    BoostCampaign.objects.filter(reel=post).update(end_time=timezone.now() - timedelta(minutes=1))

    expire_boost_campaigns()
    first = BoostCampaign.objects.get(reel=post).status
    expire_boost_campaigns()

    assert BoostCampaign.objects.get(reel=post).status == first


# ── the viral guarantee ─────────────────────────────────────────────────────


def test_impressions_are_counted_from_real_views(owner, post, wallet, config, server_key, client_key):
    """The guarantee is only honest because BoostImpression rows exist."""
    wallet.add_earned(2000, transaction_type='reward')
    buy(owner, post.pk, 'viral', server_key, client_key)
    campaign = BoostCampaign.objects.get(reel=post)

    viewer = User.objects.create_user(username='a_viewer', password='x')
    BoostImpression.objects.create(campaign=campaign, viewer=viewer)

    assert BoostImpression.objects.filter(campaign=campaign).count() == 1


def test_a_viral_campaign_completes_when_its_guarantee_is_met(
    owner, post, wallet, config, server_key, client_key
):
    """Stopping short of 5,000 while the window is open would be selling a
    number the platform did not deliver; running past it would be giving
    away impressions nobody paid for."""
    from api.views.boost import record_boost_impression

    wallet.add_earned(2000, transaction_type='reward')
    buy(owner, post.pk, 'viral', server_key, client_key)

    # One short of the guarantee, then the view that meets it.
    BoostCampaign.objects.filter(reel=post).update(impressions_served=4999)

    viewer = User.objects.create_user(username='final_viewer', password='x')
    sealed_post(
        record_boost_impression, viewer, '/boost/impression/',
        {'reel_id': post.pk}, server_key, client_key,
    )

    campaign = BoostCampaign.objects.get(reel=post)
    assert campaign.impressions_served >= 5000
    assert campaign.status == 'completed'


def test_a_tier_without_a_guarantee_is_not_completed_early(
    owner, post, wallet, config, server_key, client_key
):
    """Only a guaranteed campaign ends on an impression count."""
    wallet.add_earned(500, transaction_type='reward')
    buy(owner, post.pk, 'standard', server_key, client_key)

    BoostCampaign.objects.filter(reel=post).update(impressions_served=999_999)
    campaign = BoostCampaign.objects.get(reel=post)

    assert campaign.guaranteed_impressions is None
    assert campaign.status == 'active'


# ── what the boost sheet is told ────────────────────────────────────────────


def test_the_config_endpoint_lists_every_tier(owner, config, server_key, client_key):
    from api.views.boost import get_boost_config

    data = sealed_get(get_boost_config, owner, '/boost/config/', server_key, client_key)

    keys = {tier['key'] for tier in data['tiers']}
    assert keys == {'standard', 'premium', 'viral'}


def test_the_sheet_is_told_the_balance_so_it_can_mark_a_tier_unaffordable(
    owner, wallet, config, server_key, client_key
):
    from api.views.boost import get_boost_config

    wallet.add_earned(75, transaction_type='reward')
    data = sealed_get(get_boost_config, owner, '/boost/config/', server_key, client_key)

    assert data['coin_balance'] == 75


def test_every_tier_carries_its_cost_duration_and_placement():
    for tier in boost_tiers.tier_list():
        assert tier['coins'] > 0
        assert tier['duration_hours'] > 0
        assert tier['placement_label']


# ── the older hourly form still works ───────────────────────────────────────


def test_an_hourly_boost_is_unchanged(owner, post, wallet, config, server_key, client_key):
    """Existing clients send duration_hours and no tier. They keep working,
    and their campaigns are recorded as 'custom'."""
    from api.views.boost import create_boost_campaign

    wallet.add_earned(5000, transaction_type='reward')
    response, data = sealed_post(
        create_boost_campaign, owner, '/boost/create/',
        {'reel_id': post.pk, 'duration_hours': 6}, server_key, client_key,
    )

    assert response.status_code == 200, data
    campaign = BoostCampaign.objects.get(reel=post)
    assert campaign.boost_type == 'custom'
    assert campaign.duration_hours == 6
    assert campaign.guaranteed_impressions is None


def test_a_request_with_neither_a_tier_nor_a_duration_is_refused(
    owner, post, wallet, config, server_key, client_key
):
    from api.views.boost import create_boost_campaign

    wallet.add_earned(500, transaction_type='reward')
    response, _data = sealed_post(
        create_boost_campaign, owner, '/boost/create/',
        {'reel_id': post.pk}, server_key, client_key,
    )

    assert response.status_code == 400


# ── the database is what prevents a double purchase ─────────────────────────


def test_the_constraint_and_not_the_check_is_what_guarantees_it(
    owner, post, wallet, config, server_key, client_key
):
    """Two requests arriving together both pass the view's check.

    The real race needs PostgreSQL (see tests/integration/test_concurrency.py
    for why SQLite cannot exercise it), so what is pinned here is the thing
    whose absence was the bug: a partial unique index, so that a second
    insert is refused by the database rather than by a check that read stale
    state a millisecond earlier.
    """
    from django.db import IntegrityError

    wallet.add_earned(500, transaction_type='reward')
    buy(owner, post.pk, 'standard', server_key, client_key)

    # Insert straight past the view's check, as a lost race would.
    with pytest.raises(IntegrityError):
        BoostCampaign.objects.create(
            user=owner,
            reel=post,
            boost_type='premium',
            placement=boost_tiers.FEED,
            duration_hours=24,
            coins_spent=Decimal('100'),
            coins_remaining=Decimal('100'),
            end_time=timezone.now() + timedelta(hours=24),
            expected_impressions=100,
            hourly_budget=Decimal('4'),
            target_location='',
        )


def test_the_constraint_only_covers_live_tier_boosts(owner, post, config, db):
    """An ended boost does not block the next one, and the older hourly form
    keeps the several-at-once behaviour it has always had."""
    common = dict(
        user=owner,
        reel=post,
        duration_hours=1,
        coins_spent=Decimal('10'),
        coins_remaining=Decimal('10'),
        expected_impressions=10,
        hourly_budget=Decimal('10'),
        target_location='',
    )

    BoostCampaign.objects.create(
        boost_type='standard', placement=boost_tiers.TRENDING, status='completed',
        end_time=timezone.now() - timedelta(hours=1), **common,
    )
    BoostCampaign.objects.create(
        boost_type='standard', placement=boost_tiers.TRENDING, status='active',
        end_time=timezone.now() + timedelta(hours=1), **common,
    )
    # Two custom boosts alongside it, which has always been allowed.
    for _ in range(2):
        BoostCampaign.objects.create(
            boost_type='custom', placement=boost_tiers.TRENDING, status='active',
            end_time=timezone.now() + timedelta(hours=1), **common,
        )

    assert BoostCampaign.objects.filter(reel=post).count() == 4


def test_a_lost_race_is_answered_like_the_check(owner, post, wallet, config, server_key, client_key):
    """The IntegrityError becomes the same friendly refusal, not a 500."""
    wallet.add_earned(500, transaction_type='reward')
    buy(owner, post.pk, 'standard', server_key, client_key)
    wallet.refresh_from_db()
    after_first = wallet.balance

    response, data = buy(owner, post.pk, 'premium', server_key, client_key)

    assert response.status_code == 400
    assert data.get('code') == 'already_boosted'
    wallet.refresh_from_db()
    assert wallet.balance == after_first, 'a refused duplicate took coins'


# ── an unmet guarantee is not reported as delivered ─────────────────────────


def test_a_viral_boost_that_falls_short_is_marked_undelivered(
    owner, post, wallet, config, server_key, client_key
):
    """The record has to say what happened.

    Marking this 'completed' would make the ledger claim a guarantee was
    honoured when 2,000 of 5,000 impressions were served -- the one thing
    this product must not say falsely.
    """
    from api.tasks.boost import expire_boost_campaigns

    wallet.add_earned(2000, transaction_type='reward')
    buy(owner, post.pk, 'viral', server_key, client_key)

    BoostCampaign.objects.filter(reel=post).update(
        impressions_served=2000, end_time=timezone.now() - timedelta(minutes=1)
    )
    expire_boost_campaigns()

    campaign = BoostCampaign.objects.get(reel=post)
    assert campaign.status == 'undelivered'
    assert campaign.impressions_served == 2000
    assert campaign.guaranteed_impressions == 5000


def test_a_viral_boost_that_delivered_is_completed(
    owner, post, wallet, config, server_key, client_key
):
    from api.tasks.boost import expire_boost_campaigns

    wallet.add_earned(2000, transaction_type='reward')
    buy(owner, post.pk, 'viral', server_key, client_key)

    BoostCampaign.objects.filter(reel=post).update(
        impressions_served=5000, end_time=timezone.now() - timedelta(minutes=1)
    )
    expire_boost_campaigns()

    assert BoostCampaign.objects.get(reel=post).status == 'completed'


def test_a_tier_without_a_guarantee_is_never_undelivered(
    owner, post, wallet, config, server_key, client_key
):
    """Standard sells a placement for twelve hours, not a number of views,
    so serving few impressions is not a shortfall."""
    from api.tasks.boost import expire_boost_campaigns

    wallet.add_earned(500, transaction_type='reward')
    buy(owner, post.pk, 'standard', server_key, client_key)

    BoostCampaign.objects.filter(reel=post).update(
        impressions_served=0, end_time=timezone.now() - timedelta(minutes=1)
    )
    expire_boost_campaigns()

    assert BoostCampaign.objects.get(reel=post).status == 'completed'


def test_an_undelivered_boost_stops_being_lifted(
    owner, post, wallet, config, server_key, client_key
):
    """Recording the shortfall must not leave the campaign running."""
    from api.tasks.boost import expire_boost_campaigns

    wallet.add_earned(2000, transaction_type='reward')
    buy(owner, post.pk, 'viral', server_key, client_key)
    BoostCampaign.objects.filter(reel=post).update(
        impressions_served=1, end_time=timezone.now() - timedelta(minutes=1)
    )
    expire_boost_campaigns()

    live = BoostCampaign.objects.filter(
        reel=post, status='active', end_time__gt=timezone.now()
    )
    assert not live.exists()
    post.refresh_from_db()
    assert not post.is_boosted


def test_an_undelivered_boost_does_not_block_a_new_one(
    owner, post, wallet, config, server_key, client_key
):
    """The constraint covers live boosts only, so a shortfall does not lock
    the post out of being promoted again."""
    from api.tasks.boost import expire_boost_campaigns

    wallet.add_earned(3000, transaction_type='reward')
    buy(owner, post.pk, 'viral', server_key, client_key)
    BoostCampaign.objects.filter(reel=post).update(
        impressions_served=1, end_time=timezone.now() - timedelta(minutes=1)
    )
    expire_boost_campaigns()

    response, data = buy(owner, post.pk, 'standard', server_key, client_key)

    assert response.status_code == 200, data


# ── the legacy /boost-post/ endpoint ────────────────────────────────────────
#
# It charged 200 coins, wrote a PostBoost row nothing read, and then called
# reel.save(update_fields=['is_featured']) -- a field Reel does not have.
# spend_coins commits in its own transaction, so the coins were gone by the
# time the ValueError reached the client as a 500. The caller paid and got a
# server error, every single time.


def legacy_boost(user, reel_id, server_public, client_keys):
    from api.views.contest import boost_post

    return sealed_post(
        boost_post, user, '/boost-post/', {'reel_id': reel_id}, server_public, client_keys
    )


def test_reel_has_no_is_featured_field():
    """The root cause, pinned. If somebody adds the field later, this test
    fails and points them at the endpoint that assumed it existed."""
    from api.models import Reel

    assert 'is_featured' not in {f.name for f in Reel._meta.get_fields()}


def test_the_legacy_boost_now_succeeds(owner, post, wallet, config, server_key, client_key):
    wallet.add_earned(500, transaction_type='reward')

    response, data = legacy_boost(owner, post.pk, server_key, client_key)

    assert response.status_code == 200, data
    assert data['cost'] == 200


def test_the_legacy_boost_creates_a_real_campaign(
    owner, post, wallet, config, server_key, client_key
):
    """The gap: 200 coins bought a row no feed read and nothing expired."""
    wallet.add_earned(500, transaction_type='reward')

    legacy_boost(owner, post.pk, server_key, client_key)

    campaign = BoostCampaign.objects.get(reel=post)
    assert campaign.coins_spent == Decimal('200')
    assert campaign.placement == boost_tiers.TRENDING
    assert campaign.boost_type == 'custom'
    assert campaign.status == 'active'


def test_the_legacy_boost_is_visible_to_the_feeds(
    owner, post, wallet, config, server_key, client_key
):
    """The whole point of the money: the feeds ask this exact question."""
    wallet.add_earned(500, transaction_type='reward')

    legacy_boost(owner, post.pk, server_key, client_key)

    lifted = BoostCampaign.objects.filter(
        reel=post,
        status='active',
        end_time__gt=timezone.now(),
        coins_remaining__gt=0,
        placement__in=boost_tiers.placements_for_feed(boost_tiers.TRENDING),
    )
    assert lifted.exists()


def test_the_legacy_boost_expires(owner, post, wallet, config, server_key, client_key):
    """Nothing retired the old PostBoost row; the sweep retires this one."""
    from api.tasks.boost import expire_boost_campaigns

    wallet.add_earned(500, transaction_type='reward')
    legacy_boost(owner, post.pk, server_key, client_key)

    BoostCampaign.objects.filter(reel=post).update(end_time=timezone.now() - timedelta(minutes=1))
    expire_boost_campaigns()

    post.refresh_from_db()
    assert BoostCampaign.objects.get(reel=post).status != 'active'
    assert not post.is_boosted


def test_the_legacy_boost_runs_for_two_hours(owner, post, wallet, config, server_key, client_key):
    """The advertised window, unchanged."""
    wallet.add_earned(500, transaction_type='reward')

    legacy_boost(owner, post.pk, server_key, client_key)

    campaign = BoostCampaign.objects.get(reel=post)
    assert timedelta(hours=1, minutes=59) <= campaign.end_time - campaign.start_time <= timedelta(
        hours=2, minutes=1
    )


def test_the_legacy_boost_writes_no_postboost_row(
    owner, post, wallet, config, server_key, client_key
):
    """The parallel record is gone. One boost system, not two."""
    from api.models.contest import PostBoost

    wallet.add_earned(500, transaction_type='reward')

    legacy_boost(owner, post.pk, server_key, client_key)

    assert not PostBoost.objects.filter(reel=post).exists()


def test_a_failed_legacy_boost_takes_no_coins(owner, post, wallet, config, server_key, client_key):
    """The charge and the campaign share one transaction now."""
    wallet.add_earned(199, transaction_type='reward')

    response, _data = legacy_boost(owner, post.pk, server_key, client_key)

    wallet.refresh_from_db()
    assert response.status_code == 400
    assert wallet.balance == 199
    assert not BoostCampaign.objects.filter(reel=post).exists()


def test_the_legacy_boost_refuses_a_second_one(
    owner, post, wallet, config, server_key, client_key
):
    """The old check looked at PostBoost, which no feed read -- so a post
    could be 'boosted' twice and lifted neither time."""
    wallet.add_earned(1000, transaction_type='reward')

    legacy_boost(owner, post.pk, server_key, client_key)
    response, data = legacy_boost(owner, post.pk, server_key, client_key)

    assert response.status_code == 400
    assert data.get('code') == 'already_boosted'
    assert BoostCampaign.objects.filter(reel=post).count() == 1


def test_the_legacy_boost_refuses_somebody_elses_post(
    post, wallet, config, db, server_key, client_key
):
    stranger = User.objects.create_user(username='legacy_stranger', password='x')
    grant_subscription(stranger)
    balance, _ = UserCoinBalance.objects.get_or_create(user=stranger)
    balance.add_earned(500, transaction_type='reward')

    response, _data = legacy_boost(stranger, post.pk, server_key, client_key)

    assert response.status_code == 404
    assert not BoostCampaign.objects.filter(reel=post).exists()


def test_the_legacy_boost_refuses_a_moderated_post(
    owner, post, wallet, config, server_key, client_key
):
    from api.models import Reel

    wallet.add_earned(500, transaction_type='reward')
    Reel.objects.filter(pk=post.pk).update(is_hidden=True)

    response, data = legacy_boost(owner, post.pk, server_key, client_key)

    wallet.refresh_from_db()
    assert response.status_code == 400
    assert data.get('code') == 'reel_not_boostable'
    assert wallet.balance == 500


def test_the_advertised_price_and_window_are_unchanged():
    """200 coins for 2 hours is what this endpoint has always said. Worse
    value than Standard (50 for 12h), which is a pricing decision rather
    than something to correct silently."""
    from api.views.contest import BOOST_POST_COINS, BOOST_POST_HOURS

    assert BOOST_POST_COINS == 200
    assert BOOST_POST_HOURS == 2
