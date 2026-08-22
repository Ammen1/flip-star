"""
Tests for common/security/e2e_encryption.py.

Covers the round trip, and each way a real attacker or a real bug would break
it: tampered ciphertext, wrong checksum, replayed nonce, malformed input, and
missing/misconfigured server keys.
"""

import pytest

from common.exceptions import DecryptionError, ReplayDetected
from common.security import (
    decrypt_payload,
    encrypt_payload,
    generate_keypair,
    get_server_private_key,
    get_server_public_key,
)
from common.security import e2e_encryption as e2e

pytestmark = pytest.mark.unit


@pytest.fixture
def parties():
    """Two independent key pairs, standing in for two services talking to each other."""
    a_public, a_private = generate_keypair()
    b_public, b_private = generate_keypair()
    return {'a': (a_public, a_private), 'b': (b_public, b_private)}


@pytest.fixture(autouse=True)
def _clear_key_cache():
    """Every test starts with no cached server key pair."""
    e2e.reset_key_cache()
    yield
    e2e.reset_key_cache()


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------

def test_round_trip_recovers_original_data(parties):
    a_public, a_private = parties['a']
    b_public, b_private = parties['b']

    payload = {'TransactionReference': 'TX-001', 'PaidAmount': '150.00'}

    sealed = encrypt_payload(payload, receiver_public_key_b64=b_public, sender_private_key_b64=a_private)

    plaintext = decrypt_payload(
        sealed.encrypted, sealed.nonce, a_public, sealed.checksum, b_private,
    )

    assert plaintext == '{"PaidAmount":"150.00","TransactionReference":"TX-001"}'


def test_encrypted_payload_serialises_to_a_plain_dict(parties):
    a_public, a_private = parties['a']
    b_public, _ = parties['b']

    sealed = encrypt_payload({'x': 1}, receiver_public_key_b64=b_public, sender_private_key_b64=a_private)

    assert set(sealed.to_dict()) == {'encrypted', 'nonce', 'checksum'}


def test_each_encryption_uses_a_fresh_nonce(parties):
    a_public, a_private = parties['a']
    b_public, _ = parties['b']

    first = encrypt_payload({'x': 1}, receiver_public_key_b64=b_public, sender_private_key_b64=a_private)
    second = encrypt_payload({'x': 1}, receiver_public_key_b64=b_public, sender_private_key_b64=a_private)

    assert first.nonce != second.nonce
    assert first.encrypted != second.encrypted


# ---------------------------------------------------------------------------
# Tampering and authentication
# ---------------------------------------------------------------------------

def test_tampered_ciphertext_is_rejected(parties):
    a_public, a_private = parties['a']
    b_public, b_private = parties['b']

    sealed = encrypt_payload({'amount': 100}, receiver_public_key_b64=b_public, sender_private_key_b64=a_private)

    tampered = sealed.encrypted[:-4] + ('AAAA' if sealed.encrypted[-4:] != 'AAAA' else 'BBBB')

    with pytest.raises(DecryptionError):
        decrypt_payload(tampered, sealed.nonce, a_public, sealed.checksum, b_private)


def test_wrong_sender_key_is_rejected(parties):
    a_public, a_private = parties['a']
    b_public, b_private = parties['b']
    _, mallory_private = generate_keypair()

    sealed = encrypt_payload({'amount': 100}, receiver_public_key_b64=b_public, sender_private_key_b64=a_private)

    # Decrypting as though Mallory sent it, instead of A -- must fail, not
    # silently "succeed" with garbage.
    with pytest.raises(DecryptionError):
        decrypt_payload(sealed.encrypted, sealed.nonce, a_public, sealed.checksum, mallory_private)


def test_wrong_checksum_is_rejected_even_when_decryption_succeeds(parties):
    a_public, a_private = parties['a']
    b_public, b_private = parties['b']

    sealed = encrypt_payload({'amount': 100}, receiver_public_key_b64=b_public, sender_private_key_b64=a_private)

    with pytest.raises(DecryptionError, match='[Cc]hecksum'):
        decrypt_payload(sealed.encrypted, sealed.nonce, a_public, '0' * 64, b_private)


# ---------------------------------------------------------------------------
# Replay protection
# ---------------------------------------------------------------------------

def test_second_decrypt_of_the_same_nonce_is_a_replay(parties):
    a_public, a_private = parties['a']
    b_public, b_private = parties['b']

    sealed = encrypt_payload({'amount': 100}, receiver_public_key_b64=b_public, sender_private_key_b64=a_private)

    # First delivery: fine.
    decrypt_payload(sealed.encrypted, sealed.nonce, a_public, sealed.checksum, b_private)

    # Attacker (or a retry, or a redelivered queue message) resends the exact
    # same bytes.
    with pytest.raises(ReplayDetected):
        decrypt_payload(sealed.encrypted, sealed.nonce, a_public, sealed.checksum, b_private)


def test_check_replay_false_allows_re_verification(parties):
    a_public, a_private = parties['a']
    b_public, b_private = parties['b']

    sealed = encrypt_payload({'amount': 100}, receiver_public_key_b64=b_public, sender_private_key_b64=a_private)

    decrypt_payload(sealed.encrypted, sealed.nonce, a_public, sealed.checksum, b_private)

    # Explicitly opted out of the replay check -- must not raise.
    plaintext = decrypt_payload(
        sealed.encrypted, sealed.nonce, a_public, sealed.checksum, b_private, check_replay=False,
    )
    assert plaintext


# ---------------------------------------------------------------------------
# Malformed input
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('field', ['encrypted', 'nonce', 'sender_public', 'receiver_private'])
def test_malformed_base64_is_rejected(parties, field):
    a_public, a_private = parties['a']
    b_public, b_private = parties['b']
    sealed = encrypt_payload({'x': 1}, receiver_public_key_b64=b_public, sender_private_key_b64=a_private)

    args = {
        'encrypted_b64': sealed.encrypted,
        'nonce_b64': sealed.nonce,
        'sender_public_key_b64': a_public,
        'expected_checksum': sealed.checksum,
        'receiver_private_key_b64': b_private,
    }
    field_map = {
        'encrypted': 'encrypted_b64',
        'nonce': 'nonce_b64',
        'sender_public': 'sender_public_key_b64',
        'receiver_private': 'receiver_private_key_b64',
    }
    args[field_map[field]] = 'not valid base64!!! ###'

    with pytest.raises(DecryptionError):
        decrypt_payload(**args)


def test_malformed_key_is_rejected_on_encrypt():
    with pytest.raises(DecryptionError):
        encrypt_payload({'x': 1}, receiver_public_key_b64='AA==', sender_private_key_b64='AA==')


# ---------------------------------------------------------------------------
# Server key pair (delegates to infrastructure.keys.key_manager)
# ---------------------------------------------------------------------------
# Redis storage, pair validation, and the startup state machine (missing /
# partial / mismatched keypair, concurrent init, etc.) are covered in full by
# tests/unit/test_key_management.py. These two only confirm the delegation
# itself: get_server_public_key/get_server_private_key return whatever the
# KeyManagementService singleton holds, and that value is actually usable for
# encryption -- not just plumbing that happens to type-check.

@pytest.fixture
def _server_keypair():
    """Initialize the shared key_manager singleton against a fresh fake Redis."""
    import fakeredis

    from infrastructure.keys import redis_store

    redis_store.set_client(fakeredis.FakeRedis())
    e2e.key_manager.reset()
    e2e.key_manager.initialize()
    yield
    e2e.key_manager.reset()
    redis_store.reset_client()


def test_server_key_accessors_delegate_to_key_manager(_server_keypair):
    assert get_server_public_key() == e2e.key_manager.get_public_key()
    assert get_server_private_key() == e2e.key_manager.get_private_key()


def test_server_keypair_is_usable_for_encryption(_server_keypair, parties):
    a_public, a_private = parties['a']

    sealed = encrypt_payload(
        {'secret': 'value'},
        receiver_public_key_b64=get_server_public_key(),
        sender_private_key_b64=a_private,
    )
    plaintext = decrypt_payload(
        sealed.encrypted, sealed.nonce, a_public, sealed.checksum, get_server_private_key(),
    )
    assert plaintext == '{"secret":"value"}'


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

def test_generate_keypair_produces_usable_keys():
    public_key, private_key = generate_keypair()

    # Round-trip with itself: encrypting to your own public key and decrypting
    # with your own private key is a degenerate but valid case.
    sealed = encrypt_payload({'ok': True}, receiver_public_key_b64=public_key, sender_private_key_b64=private_key)
    plaintext = decrypt_payload(sealed.encrypted, sealed.nonce, public_key, sealed.checksum, private_key)

    assert plaintext == '{"ok":true}'


def test_generate_keypair_produces_distinct_pairs():
    pair_one = generate_keypair()
    pair_two = generate_keypair()

    assert pair_one != pair_two
