"""
Which plans a visitor is offered.

On-demand is a top-up on an account that already exists: no duration, nothing
granted on its own. Offered as somebody's first subscription it takes their
money and leaves them with no service, so it is left out for a request that
carries no user -- which is every first-time subscriber, on the web and inside
the SuperApp alike.

The rule lives on the API rather than in each client, because a client got it
wrong in exactly the way clients do: the web app filtered on the name
'OnDemand', `manage.py seed_subscription_tiers` renamed the tier 'OnDemand
Premium', and from then on the filter removed nothing. These tests pin the
rule to the plan's *type*, which is what the product means.

The tiers endpoint sits behind EncryptedPayloadMixin, so these drive the real
transport -- header in, sealed response out -- rather than bypassing it.
"""

import json

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient

from api.models import SubscriptionTier
from common.security.e2e_encryption import decrypt_payload

pytestmark = pytest.mark.django_db


@pytest.fixture
def ask(encrypted_client_keys):
    """Ask for the plan list, as a visitor or as an account holder, and read
    the sealed answer back.

    `encrypted_client_keys` (tests/conftest.py) stands the server keypair up in
    an in-memory Redis; without it the endpoint has no key to seal its reply.
    """
    server_public_key, public, private = encrypted_client_keys

    def _ask(user=None, route='subscription-tiers'):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        response = client.get(reverse(route), HTTP_X_CLIENT_PUBLIC_KEY=public)
        assert response.status_code == 200, response.status_code
        response.render()
        raw = json.loads(response.content)
        if isinstance(raw, dict) and {'encrypted', 'nonce', 'checksum'} <= raw.keys():
            raw = json.loads(
                decrypt_payload(
                    raw['encrypted'], raw['nonce'], server_public_key, raw['checksum'], private
                )
            )
        return {row['name'] for row in raw}

    return _ask


@pytest.fixture
def on_demand():
    """The seeded on-demand tier, named as staging has it."""
    tier = SubscriptionTier.objects.get(duration_type='ondemand')
    tier.name = 'OnDemand Premium'
    tier.is_active = True
    tier.save(update_fields=['name', 'is_active'])
    return tier


@pytest.fixture
def account_holder():
    return User.objects.create_user(username='subscriber', password='x')


def test_a_first_time_visitor_is_not_offered_on_demand(ask, on_demand):
    assert on_demand.name not in ask()


def test_the_active_alias_answers_the_same(ask, on_demand):
    """Both clients read /tiers/active/ rather than /tiers/."""
    assert on_demand.name not in ask(route='subscription-tiers-active')


def test_someone_with_an_account_still_sees_on_demand(ask, on_demand, account_holder):
    assert on_demand.name in ask(account_holder)


def test_the_rule_follows_the_plan_type_not_its_name(ask, on_demand):
    """Renaming the tier in the admin must not put it back in front of
    first-time subscribers -- which is how this broke the first time."""
    on_demand.name = 'Pay As You Go'
    on_demand.save(update_fields=['name'])

    assert 'Pay As You Go' not in ask()


def test_the_plans_a_first_subscription_can_use_are_all_still_offered(ask, on_demand):
    startable = set(
        SubscriptionTier.objects.filter(is_active=True)
        .exclude(duration_type='ondemand')
        .values_list('name', flat=True)
    )

    assert startable, 'no plans left to start a subscription with'
    assert ask() == startable


def test_an_inactive_plan_is_offered_to_nobody(ask, account_holder):
    daily = SubscriptionTier.objects.filter(duration_type='daily').first()
    daily.is_active = False
    daily.save(update_fields=['is_active'])

    assert daily.name not in ask()
    assert daily.name not in ask(account_holder)
