"""
Regression coverage for ``/subscription/status/``.

Why this file exists
--------------------
The endpoint was observed returning HTTP 500 in UAT. The frontend caught that
error and fell back to "no subscription", so a server failure was silently
converted into a valid business state -- paying users were refused Buy Coins
and pushed to the subscribe page.

The contract these tests pin:

* "no active subscription" is a business state -> 200 with
  ``has_subscription: false``, never a 500;
* an ordinary account shape (no record, expired, cancelled, missing tier)
  never produces a 500;
* a missing ``X-Client-Public-Key`` header is a client error -> 400, not 500;
* internal exception detail never reaches the client.

``/subscription/`` is on ``ENCRYPTED_ENDPOINT_PREFIXES``, so the view sits
behind ``EncryptedPayloadMixin``: requests carry the client public key header
and responses come back sealed. These tests drive that real transport rather
than bypassing it, because the encryption layer is itself a plausible source
of a 500 (a renderer raising escapes DRF's exception handler).
"""

import json
from datetime import timedelta

import fakeredis
import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from common.security.e2e_encryption import decrypt_payload, generate_keypair
from infrastructure.keys import redis_store

from api.models.subscription import SubscriptionPlan, SubscriptionTier

pytestmark = pytest.mark.django_db

URL_NAME = 'subscription-status'


# ─── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def server_public_key(db):
    """Server keypair in an in-memory Redis, matching the other e2e tests."""
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
def user():
    return User.objects.create_user(username='sub_user', email='sub@test.local', password='x')


@pytest.fixture
def tier():
    # A distinct slug: migrations seed the standard tiers, and `slug` is unique.
    obj, _ = SubscriptionTier.objects.get_or_create(
        slug='audit-monthly',
        defaults={
            'name': 'Audit Monthly',
            'price_etb': 100,
            'duration_type': 'monthly',
            'duration_days': 30,
        },
    )
    return obj


def _plan(user, tier, *, status='active', days=30):
    now = timezone.now()
    return SubscriptionPlan.objects.create(
        user=user,
        tier=tier,
        status=status,
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=days),
    )


def _get(user, client_public_key):
    c = APIClient()
    c.force_authenticate(user=user)
    return c.get(reverse(URL_NAME), HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)


def _body(response, *, server_public_key, client_private_key):
    """Plaintext body, whether the response came back sealed or not."""
    response.render()
    raw = json.loads(response.content)
    if isinstance(raw, dict) and {'encrypted', 'nonce', 'checksum'} <= raw.keys():
        return json.loads(
            decrypt_payload(
                raw['encrypted'], raw['nonce'], server_public_key,
                raw['checksum'], client_private_key,
            )
        )
    return raw


def _assert_contract(body):
    """Every 200 carries the same keys, whatever the business state."""
    assert 'has_subscription' in body, body
    assert isinstance(body['has_subscription'], bool), body
    assert 'subscription' in body, body
    if body['has_subscription']:
        sub = body['subscription']
        assert sub is not None
        for key in ('id', 'tier', 'status', 'start_date', 'end_date', 'auto_renew'):
            assert key in sub, f'missing {key} in {sub}'
    else:
        assert body['subscription'] is None


# ─── auth and transport boundaries ────────────────────────────────────────────

def test_unauthenticated_is_401_not_500(server_public_key, client_keys):
    pub, _priv = client_keys
    r = APIClient().get(reverse(URL_NAME), HTTP_X_CLIENT_PUBLIC_KEY=pub)
    assert r.status_code in (401, 403), r.status_code


def test_missing_client_key_header_is_400_not_500(server_public_key, user):
    """A client that forgets the header gets a clean client error."""
    c = APIClient()
    c.force_authenticate(user=user)
    r = c.get(reverse(URL_NAME))
    assert r.status_code == 400, r.content[:300]
    assert b'decryption_failed' in r.content


# ─── business states: none of these may 500 ───────────────────────────────────

def test_no_subscription_record_returns_200(server_public_key, client_keys, user):
    """The single most important case: never a 500 for a brand new account."""
    pub, priv = client_keys
    r = _get(user, pub)
    assert r.status_code == 200, r.content[:400]
    body = _body(r, server_public_key=server_public_key, client_private_key=priv)
    _assert_contract(body)
    assert body['has_subscription'] is False


def test_active_subscription_returns_true(server_public_key, client_keys, user, tier):
    pub, priv = client_keys
    _plan(user, tier, status='active', days=30)
    r = _get(user, pub)
    assert r.status_code == 200, r.content[:400]
    body = _body(r, server_public_key=server_public_key, client_private_key=priv)
    _assert_contract(body)
    assert body['has_subscription'] is True
    assert body['subscription']['tier']['name'] == 'Audit Monthly'


def test_expired_subscription_is_not_active(server_public_key, client_keys, user, tier):
    pub, priv = client_keys
    _plan(user, tier, status='active', days=-1)
    r = _get(user, pub)
    assert r.status_code == 200, r.content[:400]
    body = _body(r, server_public_key=server_public_key, client_private_key=priv)
    _assert_contract(body)
    assert body['has_subscription'] is False
    assert body.get('has_had_subscription') is True


def test_cancelled_subscription_is_not_active(server_public_key, client_keys, user, tier):
    pub, priv = client_keys
    _plan(user, tier, status='cancelled', days=30)
    r = _get(user, pub)
    assert r.status_code == 200, r.content[:400]
    body = _body(r, server_public_key=server_public_key, client_private_key=priv)
    _assert_contract(body)
    assert body['has_subscription'] is False


def test_active_plan_with_null_tier_does_not_500(server_public_key, client_keys, user):
    """
    The view dereferences ``subscription.tier.name`` and friends. If any row in
    production carries a null tier, that is exactly where a 500 comes from.
    """
    pub, priv = client_keys
    now = timezone.now()
    SubscriptionPlan.objects.create(
        user=user, tier=None, status='active',
        start_date=now - timedelta(days=1), end_date=now + timedelta(days=30),
    )
    r = _get(user, pub)
    assert r.status_code == 200, r.content[:400]
    _assert_contract(_body(r, server_public_key=server_public_key, client_private_key=priv))


@pytest.mark.parametrize('state', ['active', 'cancelled', 'expired', 'pending', 'suspended'])
def test_no_status_value_produces_a_500(server_public_key, client_keys, user, tier, state):
    """Whatever ``status`` a row carries, the endpoint answers 200."""
    pub, priv = client_keys
    _plan(user, tier, status=state, days=30)
    r = _get(user, pub)
    assert r.status_code == 200, f'status={state!r} -> {r.status_code}: {r.content[:300]}'
    _assert_contract(_body(r, server_public_key=server_public_key, client_private_key=priv))


# ─── safety ───────────────────────────────────────────────────────────────────

def test_response_never_leaks_a_traceback(server_public_key, client_keys, user):
    pub, _priv = client_keys
    r = _get(user, pub)
    body = r.content.decode('utf-8', 'replace').lower()
    for leak in ('traceback', 'file "', 'site-packages'):
        assert leak not in body, f'response leaked {leak!r}'


def test_repeated_calls_are_stable(server_public_key, client_keys, user, tier):
    pub, priv = client_keys
    _plan(user, tier, status='active', days=30)
    first = _get(user, pub)
    second = _get(user, pub)
    assert first.status_code == second.status_code == 200
    b1 = _body(first, server_public_key=server_public_key, client_private_key=priv)
    b2 = _body(second, server_public_key=server_public_key, client_private_key=priv)
    assert b1['has_subscription'] is b2['has_subscription'] is True
