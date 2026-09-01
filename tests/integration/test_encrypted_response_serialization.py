"""
Non-JSON-native Python objects in encrypted responses.

Staging failed with::

    Response encryption failed (status 200):
    Object of type date is not JSON serializable

The view returned 200 and DRF would have rendered it fine -- the failure was
in the encrypted path only. EncryptedJSONRenderer replaces JSONRenderer, but
encrypt_payload serialised with a bare ``json.dumps`` while DRF's renderer uses
``rest_framework.utils.encoders.JSONEncoder``, which understands date,
datetime, Decimal, UUID and friends. So the same view succeeded or failed
depending purely on whether the caller sent X-Client-Public-Key.

The concrete trigger was ``UserProfile.last_login_date`` (a DateField) in
/api/v1/gamification/status/, but ~38 hand-built response dicts across eight
view modules pass model datetimes through the same way.

These tests pin two things: encrypt_payload handles the types DRF handles, and
its output is byte-identical to what the unencrypted renderer produces -- the
wire contract must not depend on whether a response was encrypted.
"""

import datetime
import decimal
import json
import uuid

import fakeredis
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIClient

from common.security.e2e_encryption import (
    decrypt_payload,
    encrypt_payload,
    generate_keypair,
)
from infrastructure.keys import key_manager, redis_store

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# encrypt_payload accepts everything DRF's renderer accepts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'label,value,expected',
    [
        ('date', datetime.date(2026, 9, 1), '2026-09-01'),
        (
            'datetime',
            datetime.datetime(2026, 9, 1, 12, 30, tzinfo=datetime.UTC),
            '2026-09-01T12:30:00Z',
        ),
        ('time', datetime.time(12, 30), '12:30:00'),
        ('decimal', decimal.Decimal('12.34'), 12.34),
        (
            'uuid',
            uuid.UUID('12345678-1234-5678-1234-567812345678'),
            '12345678-1234-5678-1234-567812345678',
        ),
    ],
)
def test_encrypt_payload_serialises_non_native_types(label, value, expected):
    """A bare json.dumps raises TypeError on every one of these."""
    server_public, server_private = generate_keypair()
    client_public, client_private = generate_keypair()

    sealed = encrypt_payload(
        {'field': value},
        receiver_public_key_b64=client_public,
        sender_private_key_b64=server_private,
    )

    opened = json.loads(
        decrypt_payload(
            sealed.encrypted,
            sealed.nonce,
            server_public,
            sealed.checksum,
            client_private,
        )
    )

    assert opened['field'] == expected, f'{label} round-tripped incorrectly'


def test_encrypted_output_matches_the_unencrypted_renderer():
    """
    The contract must not depend on whether the response was encrypted.

    Notably this is why the views were NOT rewritten to call .isoformat():
    DRF renders an aware UTC datetime with a `Z` suffix, while .isoformat()
    emits `+00:00`. Fixing it in the views would have changed the wire format
    for unencrypted callers.
    """
    payload = {
        'a_date': datetime.date(2026, 9, 1),
        'a_datetime': datetime.datetime(2026, 9, 1, 12, 30, tzinfo=datetime.UTC),
        'an_amount': decimal.Decimal('99.50'),
        'an_id': uuid.UUID('12345678-1234-5678-1234-567812345678'),
    }

    rendered = json.loads(JSONRenderer().render(payload).decode())

    server_public, server_private = generate_keypair()
    client_public, client_private = generate_keypair()
    sealed = encrypt_payload(
        payload,
        receiver_public_key_b64=client_public,
        sender_private_key_b64=server_private,
    )
    opened = json.loads(
        decrypt_payload(
            sealed.encrypted,
            sealed.nonce,
            server_public,
            sealed.checksum,
            client_private,
        )
    )

    assert opened == rendered


def test_checksum_still_validates_with_the_new_encoder():
    """
    The checksum is taken over the serialised plaintext. Changing the encoder
    changes that string for these types, so confirm the two halves still agree
    -- a mismatch would surface as a decrypt failure, not a serialisation one.
    """
    server_public, server_private = generate_keypair()
    client_public, client_private = generate_keypair()

    sealed = encrypt_payload(
        {'when': datetime.date(2026, 9, 1)},
        receiver_public_key_b64=client_public,
        sender_private_key_b64=server_private,
    )

    # Raises DecryptionError if the checksum does not match the plaintext.
    opened = json.loads(
        decrypt_payload(
            sealed.encrypted,
            sealed.nonce,
            server_public,
            sealed.checksum,
            client_private,
        )
    )
    assert opened == {'when': '2026-09-01'}


# ---------------------------------------------------------------------------
# The endpoint that actually failed
# ---------------------------------------------------------------------------


@pytest.fixture
def server_keys():
    """
    The encrypted renderer needs the server's own keypair, which normally lives
    in Redis. Same setup the other encrypted-endpoint suites use.
    """
    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def user_with_login_date():
    user = User.objects.create_user(username='gamer', password='x')
    profile = user.profile
    # The exact field in the staging failure: a DateField, populated.
    profile.last_login_date = timezone.localdate()
    profile.save(update_fields=['last_login_date'])
    return user


def test_gamification_status_encrypts_with_a_populated_date(user_with_login_date, server_keys):
    """
    Reproduces the staging failure end to end.

    Before the fix this returned 200 carrying
    {'error': 'Secure transport is temporarily unavailable. Please retry.'}
    -- the renderer's fallback -- rather than an encrypted body.
    """
    client_public, client_private = generate_keypair()
    api = APIClient()
    api.force_authenticate(user=user_with_login_date)

    response = api.get(
        '/api/v1/gamification/status/',
        HTTP_X_CLIENT_PUBLIC_KEY=client_public,
    )

    assert response.status_code == 200
    body = json.loads(response.content)

    assert 'error' not in body, f'encryption fell back to an error body: {body}'
    assert {'encrypted', 'nonce', 'checksum'} <= set(body)

    opened = json.loads(
        decrypt_payload(
            body['encrypted'],
            body['nonce'],
            server_keys,
            body['checksum'],
            client_private,
        )
    )

    last_login = opened['login_streak']['last_login']
    assert isinstance(last_login, str)
    # ISO-8601 calendar date, not a repr of a Python object.
    datetime.date.fromisoformat(last_login)


def test_gamification_status_encrypts_with_a_null_date(db, server_keys):
    """The nullable branch: a profile that has never claimed a login bonus."""
    user = User.objects.create_user(username='newcomer', password='x')
    assert user.profile.last_login_date is None

    client_public, client_private = generate_keypair()
    api = APIClient()
    api.force_authenticate(user=user)

    response = api.get(
        '/api/v1/gamification/status/',
        HTTP_X_CLIENT_PUBLIC_KEY=client_public,
    )

    assert response.status_code == 200
    body = json.loads(response.content)
    assert 'error' not in body

    opened = json.loads(
        decrypt_payload(
            body['encrypted'],
            body['nonce'],
            server_keys,
            body['checksum'],
            client_private,
        )
    )
    assert opened['login_streak']['last_login'] is None
