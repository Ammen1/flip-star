"""
Organization coin configuration: inheritance, ceilings, budget and idempotency.

What this is not
----------------
It is not a second coin system. Three things already existed and are untouched:

  CampaignScoringConfig   leaderboard SCORE weights, already per-campaign
  WalletConfig.cost_*     what an engagement costs the actor
  UserCoinBalance         the balances themselves

This adds the missing axis -- what an engagement PAYS, per organization, with
per-campaign overrides -- and the guards around it.

Rewards ship off
----------------
Every reward defaults to 0 and `rewards_enabled` defaults False, so none of
this pays anything until an organization opts in. Several tests below exist
specifically to prove that.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

from api.models.campaign import Campaign
from api.models.coin_config import CampaignRewardGrant, CoinConfiguration
from api.models.contest import UserCoinBalance
from api.models.organization import Organization
from api.models.wallet import WalletConfig
from api.services.coin_config import (
    CoinConfigError,
    award,
    default_for_organization,
    resolve_for_campaign,
    snapshot_for_campaign,
    usage_for_campaign,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def org_a():
    return Organization.objects.create(name='Coin Org A', code='COIN-A', status='active')


@pytest.fixture
def org_b():
    return Organization.objects.create(name='Coin Org B', code='COIN-B', status='active')


@pytest.fixture
def fan():
    return User.objects.create_user(username='coin_fan', password='x')


def make_campaign(organization, title='Campaign'):
    return Campaign.objects.create(
        title=title,
        description='d',
        prize_title='p',
        prize_description='pd',
        campaign_type='daily',
        start_date=timezone.now(),
        entry_deadline=timezone.now() + timedelta(days=7),
        organization=organization,
    )


def org_default(organization, **values):
    return CoinConfiguration.objects.create(organization=organization, campaign=None, **values)


def campaign_config(campaign, **values):
    return CoinConfiguration.objects.create(
        organization=campaign.organization, campaign=campaign, **values
    )


def balance_of(user):
    return UserCoinBalance.objects.get(user=user).balance


# ---------------------------------------------------------------------------
# Off by default
# ---------------------------------------------------------------------------


def test_a_campaign_with_no_configuration_pays_nothing(org_a, fan):
    """
    The shipped state.

    This module must not change platform behaviour merely by existing --
    engagement pays nothing today, and it still pays nothing after these
    models land.
    """
    campaign = make_campaign(org_a)

    assert award(campaign, fan, 'like', reference='reel-1') == 0


def test_rewards_are_disabled_by_default(org_a):
    config = org_default(org_a)

    assert config.rewards_enabled is False
    assert config.like_reward == 0


def test_configured_rates_still_pay_nothing_while_disabled(org_a, fan):
    """
    Setting a rate is not the same as switching rewards on.

    Enabling means the platform starts minting coins on every like, so it is a
    separate, deliberate act.
    """
    campaign = make_campaign(org_a)
    campaign_config(campaign, like_reward=5, rewards_enabled=False)

    assert award(campaign, fan, 'like', reference='reel-1') == 0
    assert balance_of(fan) == UserCoinBalance.objects.get(user=fan).balance


# ---------------------------------------------------------------------------
# Inheritance
# ---------------------------------------------------------------------------


def test_a_campaign_inherits_its_organizations_defaults(org_a):
    org_default(org_a, like_reward=1, comment_reward=2, share_reward=5, gift_reward=10)
    campaign = make_campaign(org_a)

    resolved = resolve_for_campaign(campaign)

    assert resolved['like_reward'] == 1
    assert resolved['share_reward'] == 5
    assert resolved['source'] == 'organization'


def test_a_campaign_override_wins(org_a):
    org_default(org_a, like_reward=1, share_reward=5)
    campaign = make_campaign(org_a)
    campaign_config(campaign, like_reward=2, share_reward=10)

    resolved = resolve_for_campaign(campaign)

    assert resolved['like_reward'] == 2
    assert resolved['share_reward'] == 10
    assert resolved['source'] == 'campaign'


def test_two_campaigns_in_one_organization_can_differ(org_a):
    """The point of per-campaign configuration."""
    org_default(org_a, like_reward=1)
    a1 = make_campaign(org_a, 'A1')
    a2 = make_campaign(org_a, 'A2')
    campaign_config(a1, like_reward=2)
    campaign_config(a2, like_reward=5)

    assert resolve_for_campaign(a1)['like_reward'] == 2
    assert resolve_for_campaign(a2)['like_reward'] == 5


def test_two_organizations_can_run_different_economies(org_a, org_b):
    """Organization A's rates must not reach Organization B."""
    org_default(org_a, like_reward=1)
    org_default(org_b, like_reward=9)

    assert resolve_for_campaign(make_campaign(org_a))['like_reward'] == 1
    assert resolve_for_campaign(make_campaign(org_b))['like_reward'] == 9


def test_a_platform_campaign_falls_back_to_platform_defaults():
    """Every campaign predating organizations has organization NULL."""
    campaign = make_campaign(None)

    resolved = resolve_for_campaign(campaign)

    assert resolved['source'] == 'platform'
    assert resolved['like_reward'] == 0


def test_only_one_default_per_organization(org_a):
    """Two defaults would make "the organization's rates" ambiguous."""
    from django.db import IntegrityError, transaction

    org_default(org_a)

    with pytest.raises(IntegrityError), transaction.atomic():
        org_default(org_a)


# ---------------------------------------------------------------------------
# Snapshotting
# ---------------------------------------------------------------------------


def test_going_live_freezes_the_rates(org_a):
    org_default(org_a, like_reward=3, rewards_enabled=True)
    campaign = make_campaign(org_a)

    snapshot = snapshot_for_campaign(campaign)

    assert snapshot.like_reward == 3
    assert snapshot.locked_at is not None


def test_changing_a_default_does_not_repay_a_running_campaign(org_a):
    """
    The rule that protects participants.

    A rate change must not retroactively alter what people have already
    earned toward.
    """
    default = org_default(org_a, like_reward=3, rewards_enabled=True)
    campaign = make_campaign(org_a)
    snapshot_for_campaign(campaign)

    default.like_reward = 50
    default.save()

    assert resolve_for_campaign(campaign)['like_reward'] == 3


def test_snapshotting_twice_keeps_the_first(org_a):
    org_default(org_a, like_reward=3)
    campaign = make_campaign(org_a)
    first = snapshot_for_campaign(campaign)

    again = snapshot_for_campaign(campaign)

    assert again.pk == first.pk
    assert again.locked_at == first.locked_at


# ---------------------------------------------------------------------------
# Super Admin ceilings
# ---------------------------------------------------------------------------


def test_an_organization_cannot_exceed_the_platform_ceiling(org_a):
    """
    Super Admin sets the maximum; the organization sets its rate within it.

    Enforced in clean(), so the admin and the API refuse the same value.
    """
    platform = WalletConfig.get_config()
    platform.max_share_reward = 20
    platform.save()

    config = CoinConfiguration(organization=org_a, share_reward=1000)

    with pytest.raises(ValidationError, match='platform maximum'):
        config.full_clean()


def test_a_rate_at_the_ceiling_is_allowed(org_a):
    platform = WalletConfig.get_config()
    platform.max_share_reward = 20
    platform.save()

    CoinConfiguration(organization=org_a, share_reward=20).full_clean()


def test_the_ceiling_applies_to_campaign_overrides_too(org_a):
    platform = WalletConfig.get_config()
    platform.max_like_reward = 5
    platform.save()
    campaign = make_campaign(org_a)

    config = CoinConfiguration(organization=org_a, campaign=campaign, like_reward=99)

    with pytest.raises(ValidationError, match='platform maximum'):
        config.full_clean()


def test_a_campaign_override_must_belong_to_its_organization(org_a, org_b):
    """Otherwise resolution would hand one organization another's rates."""
    foreign = make_campaign(org_b)

    config = CoinConfiguration(organization=org_a, campaign=foreign)

    with pytest.raises(ValidationError, match='different organization'):
        config.full_clean()


def test_negative_values_are_refused(org_a):
    from api.services.coin_config import validate_against_platform_limits

    config = CoinConfiguration(organization=org_a)
    config.like_reward = -5

    with pytest.raises(CoinConfigError, match='negative'):
        validate_against_platform_limits(config)


# ---------------------------------------------------------------------------
# Paying rewards
# ---------------------------------------------------------------------------


def test_an_enabled_campaign_pays_its_configured_rate(org_a, fan):
    campaign = make_campaign(org_a)
    campaign_config(campaign, like_reward=4, rewards_enabled=True, budget=100)

    paid = award(campaign, fan, 'like', reference='reel-1')

    assert paid == 4
    assert UserCoinBalance.objects.get(user=fan).earned_balance >= 4


def test_the_same_engagement_is_paid_once(org_a, fan):
    """
    Idempotency, which is what a retry, a double-tap and a redelivered task
    all depend on.
    """
    campaign = make_campaign(org_a)
    campaign_config(campaign, like_reward=4, rewards_enabled=True, budget=100)

    first = award(campaign, fan, 'like', reference='reel-1')
    second = award(campaign, fan, 'like', reference='reel-1')

    assert (first, second) == (4, 0)
    assert CampaignRewardGrant.objects.filter(campaign=campaign, user=fan).count() == 1


def test_a_different_engagement_pays_again(org_a, fan):
    campaign = make_campaign(org_a)
    campaign_config(campaign, like_reward=4, rewards_enabled=True, budget=100)

    award(campaign, fan, 'like', reference='reel-1')
    second = award(campaign, fan, 'like', reference='reel-2')

    assert second == 4


def test_the_budget_cannot_be_exceeded(org_a):
    """
    The protection against minting unlimited coins.

    The last reward is truncated to what remains rather than refused outright,
    so a campaign spends exactly its budget and no more.
    """
    campaign = make_campaign(org_a)
    campaign_config(campaign, like_reward=10, rewards_enabled=True, budget=25)

    paid = []
    for i in range(5):
        user = User.objects.create_user(username=f'budget_fan_{i}', password='x')
        paid.append(award(campaign, user, 'like', reference=f'reel-{i}'))

    assert sum(paid) == 25, f'distributed {sum(paid)} against a budget of 25'
    config = CoinConfiguration.objects.get(campaign=campaign)
    assert config.distributed == 25
    assert config.is_exhausted


def test_an_exhausted_budget_pays_nothing_more(org_a, fan):
    campaign = make_campaign(org_a)
    campaign_config(campaign, like_reward=10, rewards_enabled=True, budget=10, distributed=10)

    assert award(campaign, fan, 'like', reference='reel-9') == 0


def test_a_declined_reward_does_not_fail_the_engagement(org_a, fan):
    """
    Returning 0 rather than raising is deliberate: a like must still happen
    when the budget has run out. It simply pays nothing.
    """
    campaign = make_campaign(org_a)
    # A budget of 0 means "no budget set", not "exhausted" -- so this uses a
    # real budget that has been fully spent.
    campaign_config(campaign, like_reward=10, rewards_enabled=True, budget=10, distributed=10)

    assert award(campaign, fan, 'like', reference='r') == 0


def test_the_per_user_cap_is_enforced(org_a, fan):
    campaign = make_campaign(org_a)
    campaign_config(
        campaign, like_reward=10, rewards_enabled=True, budget=1000, max_reward_per_user=25
    )

    paid = [award(campaign, fan, 'like', reference=f'r{i}') for i in range(5)]

    assert sum(paid) == 25


def test_the_daily_cap_is_enforced(org_a, fan):
    campaign = make_campaign(org_a)
    campaign_config(
        campaign,
        like_reward=10,
        rewards_enabled=True,
        budget=1000,
        max_daily_reward_per_user=15,
    )

    paid = [award(campaign, fan, 'like', reference=f'd{i}') for i in range(4)]

    assert sum(paid) == 15


def test_usage_reports_budget_distributed_and_remaining(org_a, fan):
    campaign = make_campaign(org_a)
    campaign_config(campaign, like_reward=10, rewards_enabled=True, budget=100)
    award(campaign, fan, 'like', reference='r1')

    usage = usage_for_campaign(campaign)

    assert usage['budget'] == 100
    assert usage['distributed'] == 10
    assert usage['remaining'] == 90
    assert usage['exhausted'] is False


# ---------------------------------------------------------------------------
# Score and reward stay separate
# ---------------------------------------------------------------------------


def test_reward_configuration_does_not_change_the_leaderboard(org_a, fan):
    """
    The distinction the specification asks for.

    A campaign may pay 4 coins per like while still scoring it at 1 on the
    leaderboard. Collapsing the two would make one impossible to change
    without moving the other.
    """
    from api.services.scoring.leaderboard import resolve_weights

    campaign = make_campaign(org_a)
    campaign_config(campaign, like_reward=4, rewards_enabled=True, budget=100)

    weights = resolve_weights(campaign)

    assert weights['likes'] == 1, 'reward configuration leaked into leaderboard scoring'
    assert weights['shares'] == 5


def test_the_existing_scoring_formula_is_untouched(org_a):
    from api.services.scoring.leaderboard import resolve_weights

    weights = resolve_weights(make_campaign(org_a))

    assert [weights['likes'], weights['comments'], weights['shares'], weights['gifts']] == [
        1,
        2,
        5,
        10,
    ]


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def test_an_organizations_default_is_reachable_only_through_itself(org_a, org_b):
    org_default(org_a, like_reward=1)

    assert default_for_organization(org_a).like_reward == 1
    assert default_for_organization(org_b) is None


def test_one_organizations_budget_does_not_fund_another(org_a, org_b, fan):
    """Spending is recorded against the campaign's own configuration row."""
    a_campaign = make_campaign(org_a)
    b_campaign = make_campaign(org_b)
    campaign_config(a_campaign, like_reward=10, rewards_enabled=True, budget=100)
    campaign_config(b_campaign, like_reward=10, rewards_enabled=True, budget=100)

    award(a_campaign, fan, 'like', reference='r1')

    assert usage_for_campaign(a_campaign)['distributed'] == 10
    assert usage_for_campaign(b_campaign)['distributed'] == 0
