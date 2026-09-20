"""
Tests for campaign level-based eligibility.

Users must meet a campaign's minimum level requirement to participate.
Level is calculated from XP: Level = (XP // 1000) + 1
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token

from api.models.campaign import Campaign
from common.security.e2e_encryption import generate_keypair


@pytest.fixture
def client_keys():
    return generate_keypair()


@pytest.fixture
def auth_client(api_client, client_keys):
    """Create an authenticated client with the given user."""

    def _make_auth_client(user):
        token, _ = Token.objects.get_or_create(user=user)
        client_public_key, _ = client_keys
        api_client.credentials(
            HTTP_AUTHORIZATION=f'Token {token.key}', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key
        )
        return api_client

    return _make_auth_client


@pytest.fixture
def make_user():
    def _make_user(username, xp=0):
        user = User.objects.create_user(username=username, password='123456')
        # Refresh to get the profile created by the post_save signal
        user.refresh_from_db()
        if hasattr(user, 'profile'):
            user.profile.xp = xp
            user.profile.level = (xp // 1000) + 1
            user.profile.save()
        return user

    return _make_user


@pytest.fixture
def make_campaign():
    def _make_campaign(min_level=1, **kwargs):
        now = timezone.now()
        defaults = {
            'title': 'Test Campaign',
            'description': 'Test description',
            'prize_title': 'Test Prize',
            'prize_description': 'Test prize description',
            'campaign_type': 'daily',
            'start_date': now,
            'entry_deadline': now + timedelta(days=7),
            'min_level': min_level,
        }
        defaults.update(kwargs)
        return Campaign.objects.create(**defaults)

    return _make_campaign


@pytest.mark.django_db
class TestCampaignLevelEligibility:
    """Tests for campaign minimum level eligibility"""

    def test_user_meets_min_level_is_eligible(self, auth_client, make_user, make_campaign):
        """User with level >= min_level should be eligible"""
        user = make_user('eligible_user', xp=2000)  # Level 3
        campaign = make_campaign(min_level=2)

        client = auth_client(user)
        response = client.get(f'/api/campaigns/{campaign.id}/')

        assert response.status_code == 200
        assert response.data['is_eligible'] is True

    def test_user_below_min_level_not_eligible(self, auth_client, make_user, make_campaign):
        """User with level < min_level should not be eligible"""
        user = make_user('low_level_user', xp=500)  # Level 1
        campaign = make_campaign(min_level=3)

        client = auth_client(user)
        response = client.get(f'/api/campaigns/{campaign.id}/')

        assert response.status_code == 200
        assert response.data['is_eligible'] is False

    def test_user_exact_min_level_is_eligible(self, auth_client, make_user, make_campaign):
        """User with level == min_level should be eligible"""
        user = make_user('exact_level_user', xp=1000)  # Level 2
        campaign = make_campaign(min_level=2)

        client = auth_client(user)
        response = client.get(f'/api/campaigns/{campaign.id}/')

        assert response.status_code == 200
        assert response.data['is_eligible'] is True

    def test_unauthenticated_user_no_level_check(self, api_client, client_keys, make_campaign):
        """Unauthenticated users should not have level eligibility check (handled on submit)"""
        campaign = make_campaign(min_level=5)

        # Unauthenticated requests to encrypted endpoints need X-Client-Public-Key
        client_public_key, _ = client_keys
        api_client.credentials(HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)

        response = api_client.get(f'/api/campaigns/{campaign.id}/')

        assert response.status_code == 200
        # Unauthenticated users don't have level, so eligibility should default to True
        # (they'll be checked when they try to submit)
        assert response.data['is_eligible'] is True

    def test_default_min_level_allows_all(self, auth_client, make_user, make_campaign):
        """Default min_level=1 allows all users"""
        user = make_user('any_user', xp=0)  # Level 1
        campaign = make_campaign()  # min_level defaults to 1

        client = auth_client(user)
        response = client.get(f'/api/campaigns/{campaign.id}/')

        assert response.status_code == 200
        assert response.data['is_eligible'] is True


@pytest.mark.django_db
class TestCampaignLevelDetail:
    """Tests for campaign detail endpoint level information"""

    def test_detail_returns_user_level_and_xp(self, auth_client, make_user, make_campaign):
        """Campaign detail should include user's level, XP, and XP for next level"""
        user = make_user('detail_user', xp=2500)  # Level 3, 2500 XP
        campaign = make_campaign(min_level=2)

        client = auth_client(user)
        response = client.get(f'/api/campaigns/{campaign.id}/')

        assert response.status_code == 200
        assert response.data['user_level'] == 3
        assert response.data['user_xp'] == 2500
        # XP for next level: Level 4 needs 3000 XP, so 3000 - 2500 = 500
        assert response.data['user_xp_for_next_level'] == 500

    def test_detail_returns_campaign_min_level(self, auth_client, make_user, make_campaign):
        """Campaign detail should include the campaign's min_level"""
        user = make_user('detail_user2', xp=0)
        campaign = make_campaign(min_level=3)

        client = auth_client(user)
        response = client.get(f'/api/campaigns/{campaign.id}/')

        assert response.status_code == 200
        # The detail endpoint returns campaign fields directly, not nested under 'campaign'
        assert response.data['min_level'] == 3


@pytest.mark.django_db
class TestCampaignListLevelInfo:
    """Tests for campaign list endpoint level information"""

    def test_list_returns_user_level(self, auth_client, make_user, make_campaign):
        """Campaign list should include user_level for each campaign"""
        user = make_user('list_user', xp=1500)  # Level 2
        campaign = make_campaign(min_level=2)

        client = auth_client(user)
        response = client.get('/api/campaigns/')

        assert response.status_code == 200
        campaigns = response.data['results'] if 'results' in response.data else response.data
        campaign_data = next(c for c in campaigns if c['id'] == campaign.id)
        assert campaign_data['user_level'] == 2

    def test_list_returns_min_level(self, auth_client, make_user, make_campaign):
        """Campaign list should include min_level for each campaign"""
        user = make_user('list_user2', xp=0)
        campaign = make_campaign(min_level=4)

        client = auth_client(user)
        response = client.get('/api/campaigns/')

        assert response.status_code == 200
        campaigns = response.data['results'] if 'results' in response.data else response.data
        campaign_data = next(c for c in campaigns if c['id'] == campaign.id)
        assert campaign_data['min_level'] == 4
