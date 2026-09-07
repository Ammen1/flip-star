"""
The coin management API: who may configure what, and what gets recorded.

Two audiences, one surface
--------------------------
Super Admin names an organization; an organization admin never does. The same
endpoint serves both, and most of this file exists to prove the second half --
that an organization id in a request from an organization account is not read
at all.

Rewards stay off
----------------
Nothing here switches payouts on. `rewards_enabled` is editable so it can be
enabled deliberately later, but it defaults False and no engagement path calls
award(). Tests at the end pin that.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.campaign import Campaign
from api.models.coin_config import CoinConfiguration, CoinConfigurationAudit
from api.models.organization import Organization, UserRealm, UserRole
from api.models.wallet import WalletConfig
from api.views import coin_management as views

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_user(username, realm=UserRealm.MEMBER, role=None, organization=None, **kwargs):
    user = User.objects.create_user(username=username, password='123456', **kwargs)
    profile = user.profile
    profile.realm = realm
    profile.role = role
    profile.organization = organization
    profile.save(update_fields=['realm', 'role', 'organization'])
    return user


@pytest.fixture
def org_a():
    return Organization.objects.create(name='Coin A', code='CA', status='active')


@pytest.fixture
def org_b():
    return Organization.objects.create(name='Coin B', code='CB', status='active')


@pytest.fixture
def superadmin():
    return User.objects.create_superuser(username='coin_root', password='x')


@pytest.fixture
def a_admin(org_a):
    return make_user('coin_a_admin', UserRealm.ORGANIZATION, UserRole.ADMIN, org_a)


@pytest.fixture
def b_admin(org_b):
    return make_user('coin_b_admin', UserRealm.ORGANIZATION, UserRole.ADMIN, org_b)


@pytest.fixture
def member():
    return make_user('coin_member', UserRealm.MEMBER)


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


def call(view, user, method='get', data=None, **kwargs):
    request = getattr(factory, method)('/x/', data or {}, format='json')
    force_authenticate(request, user=user)
    return view(request, **kwargs)


# ---------------------------------------------------------------------------
# Platform ceilings
# ---------------------------------------------------------------------------


def test_super_admin_can_read_the_platform_ceilings(superadmin):
    response = call(views.platform_coin_limits, superadmin)

    assert response.status_code == 200
    assert 'max_share_reward' in response.data


def test_super_admin_can_change_a_ceiling(superadmin):
    response = call(
        views.platform_coin_limits, superadmin, method='put', data={'max_share_reward': 42}
    )

    assert response.status_code == 200
    assert WalletConfig.get_config().max_share_reward == 42


def test_an_organization_admin_cannot_change_the_ceilings(a_admin):
    """Global limits are the platform's safety boundary, not an organization's."""
    before = WalletConfig.get_config().max_share_reward

    response = call(
        views.platform_coin_limits, a_admin, method='put', data={'max_share_reward': 9999}
    )

    assert response.status_code == 403
    assert WalletConfig.get_config().max_share_reward == before


def test_a_negative_ceiling_is_rejected(superadmin):
    response = call(
        views.platform_coin_limits, superadmin, method='put', data={'max_like_reward': -1}
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Organization configuration
# ---------------------------------------------------------------------------


def test_an_org_admin_reads_their_own_configuration(a_admin, org_a):
    response = call(views.organization_coin_config, a_admin)

    assert response.status_code == 200
    assert response.data['organization']['id'] == org_a.id


def test_an_org_admin_can_set_their_rates(a_admin, org_a):
    response = call(
        views.organization_coin_config,
        a_admin,
        method='put',
        data={'like_reward': 2, 'share_reward': 7},
    )

    assert response.status_code == 200
    config = CoinConfiguration.objects.get(organization=org_a, campaign__isnull=True)
    assert config.like_reward == 2
    assert config.share_reward == 7


def test_an_org_admin_cannot_reach_another_organization_by_id(a_admin, org_a, org_b):
    """
    The spoof.

    The URL names organization B; the account belongs to A. The id is not
    consulted for a non-platform account, so A's own configuration answers.
    """
    response = call(views.organization_coin_config, a_admin, organization_id=org_b.id)

    assert response.status_code == 200
    assert response.data['organization']['id'] == org_a.id, 'reached another organization'


def test_a_write_naming_another_organization_edits_only_your_own(a_admin, org_a, org_b):
    call(
        views.organization_coin_config,
        a_admin,
        method='put',
        data={'like_reward': 5},
        organization_id=org_b.id,
    )

    assert CoinConfiguration.objects.filter(organization=org_b).count() == 0
    assert CoinConfiguration.objects.get(organization=org_a).like_reward == 5


def test_super_admin_can_configure_any_organization(superadmin, org_b):
    response = call(
        views.organization_coin_config,
        superadmin,
        method='put',
        data={'like_reward': 3},
        organization_id=org_b.id,
    )

    assert response.status_code == 200
    assert CoinConfiguration.objects.get(organization=org_b).like_reward == 3


def test_a_member_has_no_organization_to_configure(member):
    response = call(views.organization_coin_config, member)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Validation: reject, do not clamp
# ---------------------------------------------------------------------------


def test_a_rate_above_the_platform_ceiling_is_rejected(a_admin, org_a):
    """
    Rejected with the ceiling named, not silently lowered.

    An administrator who asked for 100 and quietly got 50 would go on
    believing the campaign pays 100.
    """
    platform = WalletConfig.get_config()
    platform.max_share_reward = 50
    platform.save()

    response = call(
        views.organization_coin_config, a_admin, method='put', data={'share_reward': 100}
    )

    assert response.status_code == 400
    assert 'platform maximum' in response.data['error']
    assert not CoinConfiguration.objects.filter(organization=org_a).exists() or (
        CoinConfiguration.objects.get(organization=org_a).share_reward != 100
    )


def test_a_negative_reward_is_rejected(a_admin):
    response = call(views.organization_coin_config, a_admin, method='put', data={'like_reward': -5})

    assert response.status_code == 400
    assert response.data['code'] == 'negative'


def test_a_non_numeric_value_is_rejected(a_admin):
    response = call(
        views.organization_coin_config, a_admin, method='put', data={'like_reward': 'lots'}
    )

    assert response.status_code == 400


def test_a_rejected_change_writes_nothing(a_admin, org_a):
    """A refused edit must leave the row and the audit trail untouched."""
    call(views.organization_coin_config, a_admin, method='put', data={'like_reward': 4})
    before = CoinConfiguration.objects.get(organization=org_a).like_reward

    call(views.organization_coin_config, a_admin, method='put', data={'like_reward': -1})

    assert CoinConfiguration.objects.get(organization=org_a).like_reward == before
    assert not CoinConfigurationAudit.objects.filter(new_value='-1').exists()


def test_a_budget_below_what_was_already_paid_is_rejected(a_admin, org_a):
    config = CoinConfiguration.objects.create(organization=org_a, budget=1000, distributed=800)

    response = call(views.organization_coin_config, a_admin, method='put', data={'budget': 100})

    assert response.status_code == 400
    config.refresh_from_db()
    assert config.budget == 1000


def test_a_suspended_organization_cannot_be_configured_by_its_admin(a_admin, org_a):
    org_a.status = 'suspended'
    org_a.save()

    response = call(views.organization_coin_config, a_admin, method='put', data={'like_reward': 1})

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_a_change_is_recorded(a_admin, org_a):
    call(
        views.organization_coin_config,
        a_admin,
        method='put',
        data={'share_reward': 8, 'reason': 'Summer promotion'},
    )

    entry = CoinConfigurationAudit.objects.get(field='share_reward')
    assert entry.previous_value == '0'
    assert entry.new_value == '8'
    assert entry.changed_by_id == a_admin.id
    assert entry.reason == 'Summer promotion'
    assert entry.organization_id == org_a.id


def test_the_actor_comes_from_the_account_not_the_payload(a_admin, superadmin):
    """The audit trail must not be forgeable."""
    call(
        views.organization_coin_config,
        a_admin,
        method='put',
        data={'share_reward': 3, 'changed_by': superadmin.id},
    )

    assert CoinConfigurationAudit.objects.get(field='share_reward').changed_by_id == a_admin.id


def test_resubmitting_the_same_value_records_nothing(a_admin):
    """Re-saving an unchanged form is not an edit and must not litter the trail."""
    call(views.organization_coin_config, a_admin, method='put', data={'like_reward': 2})
    first = CoinConfigurationAudit.objects.count()

    call(views.organization_coin_config, a_admin, method='put', data={'like_reward': 2})

    assert CoinConfigurationAudit.objects.count() == first


def test_an_org_admin_sees_only_their_own_audit_history(a_admin, b_admin, org_a):
    call(views.organization_coin_config, a_admin, method='put', data={'like_reward': 1})
    call(views.organization_coin_config, b_admin, method='put', data={'like_reward': 9})

    response = call(views.coin_config_audit, a_admin)

    assert response.data['count'] >= 1
    assert all(r['organization']['id'] == org_a.id for r in response.data['results'])


def test_super_admin_sees_every_organizations_audit(superadmin, a_admin, b_admin):
    call(views.organization_coin_config, a_admin, method='put', data={'like_reward': 1})
    call(views.organization_coin_config, b_admin, method='put', data={'like_reward': 9})

    response = call(views.coin_config_audit, superadmin)

    organizations = {r['organization']['id'] for r in response.data['results']}
    assert len(organizations) == 2


# ---------------------------------------------------------------------------
# Campaign configuration
# ---------------------------------------------------------------------------


def test_a_campaign_config_seeds_from_the_organization_default(a_admin, org_a):
    call(
        views.organization_coin_config,
        a_admin,
        method='put',
        data={'like_reward': 3, 'comment_reward': 6},
    )
    campaign = make_campaign(org_a)

    call(
        views.campaign_coin_config,
        a_admin,
        method='put',
        data={'budget': 500},
        campaign_id=campaign.id,
    )

    config = CoinConfiguration.objects.get(campaign=campaign)
    assert config.like_reward == 3, 'campaign did not inherit the organization default'
    assert config.budget == 500


def test_a_campaign_config_can_diverge_from_the_default(a_admin, org_a):
    call(views.organization_coin_config, a_admin, method='put', data={'like_reward': 3})
    campaign = make_campaign(org_a)

    call(
        views.campaign_coin_config,
        a_admin,
        method='put',
        data={'like_reward': 9},
        campaign_id=campaign.id,
    )

    assert CoinConfiguration.objects.get(campaign=campaign).like_reward == 9
    assert CoinConfiguration.objects.get(organization=org_a, campaign__isnull=True).like_reward == 3


def test_another_organizations_campaign_is_not_found(a_admin, org_b):
    """404, matching the campaign API -- ids must not be enumerable."""
    foreign = make_campaign(org_b)

    response = call(views.campaign_coin_config, a_admin, campaign_id=foreign.id)

    assert response.status_code == 404


def test_another_organizations_campaign_cannot_be_configured(a_admin, org_b):
    foreign = make_campaign(org_b)

    response = call(
        views.campaign_coin_config,
        a_admin,
        method='put',
        data={'like_reward': 99},
        campaign_id=foreign.id,
    )

    assert response.status_code == 404
    assert not CoinConfiguration.objects.filter(campaign=foreign).exists()


def test_campaign_config_reports_the_effective_values(a_admin, org_a):
    campaign = make_campaign(org_a)

    response = call(views.campaign_coin_config, a_admin, campaign_id=campaign.id)

    assert response.status_code == 200
    assert 'effective' in response.data
    assert 'usage' in response.data


# ---------------------------------------------------------------------------
# Usage, grants
# ---------------------------------------------------------------------------


def test_usage_is_scoped_to_the_callers_organization(a_admin, org_a, org_b):
    make_campaign(org_a, 'Mine')
    make_campaign(org_b, 'Theirs')

    response = call(views.coin_usage_overview, a_admin)

    titles = [r['campaign']['title'] for r in response.data['campaigns']]
    assert titles == ['Mine']


def test_usage_reports_rewards_are_off(a_admin, org_a):
    """
    So a dashboard can say "rewards are currently disabled" rather than
    showing zeroes that look like a reporting bug.
    """
    make_campaign(org_a)

    response = call(views.coin_usage_overview, a_admin)

    assert response.data['rewards_enabled_anywhere'] is False


def test_reward_transactions_are_empty_while_rewards_are_off(a_admin, org_a):
    make_campaign(org_a)

    response = call(views.reward_transactions, a_admin)

    assert response.data['count'] == 0


def test_super_admin_sees_every_organizations_position(superadmin, org_a, org_b):
    response = call(views.organizations_coin_overview, superadmin)

    assert response.status_code == 200
    assert {r['organization']['code'] for r in response.data['results']} >= {'CA', 'CB'}


def test_an_org_admin_cannot_see_the_platform_overview(a_admin):
    response = call(views.organizations_coin_overview, a_admin)

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Rewards remain off, and scoring stays separate
# ---------------------------------------------------------------------------


def test_configuring_rates_does_not_enable_payouts(a_admin, org_a):
    """
    Setting a rate is not switching rewards on.

    Enabling means the platform starts minting coins on every like, so it
    stays a separate, deliberate act.
    """
    call(views.organization_coin_config, a_admin, method='put', data={'like_reward': 5})

    assert CoinConfiguration.objects.get(organization=org_a).rewards_enabled is False


def test_no_engagement_path_pays_anything(a_admin, org_a):
    """
    The guarantee for this whole change: engagement pays nothing today, and
    still pays nothing after the API landed.
    """
    from api.services.coin_config import award

    campaign = make_campaign(org_a)
    call(views.organization_coin_config, a_admin, method='put', data={'like_reward': 5})
    fan = make_user('coin_fan_api')

    assert award(campaign, fan, 'like', reference='r1') == 0


def test_coin_configuration_does_not_touch_leaderboard_scoring(a_admin, org_a):
    """Reward coins and leaderboard score remain different systems."""
    from api.services.scoring.leaderboard import resolve_weights

    campaign = make_campaign(org_a)
    call(
        views.campaign_coin_config,
        a_admin,
        method='put',
        data={'like_reward': 9},
        campaign_id=campaign.id,
    )

    assert resolve_weights(campaign)['likes'] == 1
