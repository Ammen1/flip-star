"""
Regression tests for consent tracking (api/models/legal.py UserConsent/
ConsentHistory, api/views/privacy.py) -- ported from the master branch to
replace the hardcoded stub that used to make get_consent_status always
return {'camera': False, 'storage': False, ...} regardless of what the user
had actually granted, and made update_consent a no-op that never persisted
anything ("# For now, just return success").

Uses the real `db` fixture -- the 0063_add_mentions migration dependency bug
that used to force MIGRATIONS_ARE_REPLAYABLE = False has been fixed (see
tests/conftest.py), so a real database is available.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.legal import ConsentHistory, UserConsent
from api.views.privacy import get_consent_history, get_consent_status, update_consent

pytestmark = pytest.mark.integration

factory = APIRequestFactory()


@pytest.fixture
def user(db):
    u = User.objects.create_user(username='consent_user', password='x')
    yield u
    u.delete()


def _authed(request, user):
    force_authenticate(request, user=user)
    return request


def test_consent_status_defaults_to_not_granted_when_no_record_exists(user):
    """Before any UserConsent row exists, status must read as not granted --
    not error, not fabricate a granted state."""
    request = _authed(factory.get('/privacy/consents/'), user)

    response = get_consent_status(request)

    assert response.status_code == 200, response.data
    assert response.data['consents']['camera']['granted'] is False
    assert response.data['consents']['camera']['granted_at'] is None


def test_update_consent_persists_a_real_row(user):
    """The old stub returned a success message without writing anything.
    This must actually create a UserConsent row."""
    assert not UserConsent.objects.filter(user=user, consent_type='camera').exists()

    request = _authed(
        factory.post('/privacy/consents/update/', {'type': 'camera', 'granted': True}, format='json'),
        user,
    )
    response = update_consent(request)

    assert response.status_code == 200, response.data
    consent = UserConsent.objects.get(user=user, consent_type='camera')
    assert consent.granted is True
    assert consent.granted_at is not None
    assert consent.withdrawn_at is None


def test_update_consent_round_trips_through_get_status(user):
    request = _authed(
        factory.post('/privacy/consents/update/', {'type': 'marketing', 'granted': True}, format='json'),
        user,
    )
    update_consent(request)

    status_request = _authed(factory.get('/privacy/consents/'), user)
    response = get_consent_status(status_request)

    assert response.data['consents']['marketing']['granted'] is True


def test_withdrawing_consent_sets_withdrawn_at_and_clears_granted(user):
    grant_request = _authed(
        factory.post('/privacy/consents/update/', {'type': 'analytics', 'granted': True}, format='json'),
        user,
    )
    update_consent(grant_request)

    withdraw_request = _authed(
        factory.post('/privacy/consents/update/', {'type': 'analytics', 'granted': False}, format='json'),
        user,
    )
    response = update_consent(withdraw_request)

    assert response.status_code == 200, response.data
    consent = UserConsent.objects.get(user=user, consent_type='analytics')
    assert consent.granted is False
    assert consent.withdrawn_at is not None


def test_update_consent_rejects_unknown_type(user):
    request = _authed(
        factory.post('/privacy/consents/update/', {'type': 'not_a_real_type', 'granted': True}, format='json'),
        user,
    )
    response = update_consent(request)

    assert response.status_code == 400, response.data
    assert not UserConsent.objects.filter(user=user, consent_type='not_a_real_type').exists()


def test_update_consent_creates_a_history_record_per_change(user):
    assert ConsentHistory.objects.filter(user=user, consent_type='storage').count() == 0

    grant_request = _authed(
        factory.post('/privacy/consents/update/', {'type': 'storage', 'granted': True}, format='json'),
        user,
    )
    update_consent(grant_request)

    withdraw_request = _authed(
        factory.post('/privacy/consents/update/', {'type': 'storage', 'granted': False}, format='json'),
        user,
    )
    update_consent(withdraw_request)

    history = list(
        ConsentHistory.objects.filter(user=user, consent_type='storage').order_by('created_at')
    )
    assert [h.action for h in history] == ['granted', 'withdrawn']
    assert [h.granted for h in history] == [True, False]


def test_consent_history_endpoint_returns_records_for_the_authenticated_user_only(user):
    other_user = User.objects.create_user(username='consent_other', password='x')
    try:
        ConsentHistory.objects.create(
            user=other_user, consent_type='camera', action='granted', granted=True,
        )
        mine_request = _authed(
            factory.post('/privacy/consents/update/', {'type': 'gdpr_banner', 'granted': True}, format='json'),
            user,
        )
        update_consent(mine_request)

        history_request = _authed(factory.get('/privacy/consents/history/'), user)
        response = get_consent_history(history_request)

        assert response.status_code == 200, response.data
        types_seen = {record['type'] for record in response.data['history']}
        assert types_seen == {'gdpr_banner'}
    finally:
        other_user.delete()


def test_update_consent_is_idempotent_on_repeated_identical_grants(user):
    """get_or_create + explicit update path must not create duplicate rows
    for the same (user, consent_type) -- unique_together enforces this at
    the DB level, but the view logic must not violate it on a second call."""
    for _ in range(2):
        request = _authed(
            factory.post('/privacy/consents/update/', {'type': 'privacy_policy', 'granted': True}, format='json'),
            user,
        )
        response = update_consent(request)
        assert response.status_code == 200, response.data

    assert UserConsent.objects.filter(user=user, consent_type='privacy_policy').count() == 1
    assert ConsentHistory.objects.filter(user=user, consent_type='privacy_policy').count() == 2
