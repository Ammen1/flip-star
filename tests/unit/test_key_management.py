"""
Tests for infrastructure/keys -- the application's Redis-backed identity
keypair.

Uses fakeredis instead of a live Redis server: everything this module does
(GET/MGET/SET NX PX/pipeline MULTI-EXEC/WATCH) is plain RESP protocol, no
Lua/EVAL, so a live server buys no extra coverage here and would make the
suite depend on infrastructure the rest of the unit tests don't need.

``decode_responses=True`` matters on every fake client built in this file --
without it, values come back as bytes and compare unequal to the ``str``
values the lock and validation code compares them against, so an unrelated
authoring mistake here silently masquerades as a completely different bug
(the lock never appearing to release). Same requirement applies to the real
client built in ``infrastructure.keys.redis_store.get_client()``.
"""

from __future__ import annotations

import base64
import logging
import threading

import fakeredis
import pytest
from rest_framework.test import APIClient

from infrastructure.keys import redis_store
from infrastructure.keys.exceptions import KeyManagementError
from infrastructure.keys.service import KeyManagementService, generate_keypair

pytestmark = pytest.mark.unit


@pytest.fixture
def fake_client():
    """A single in-memory Redis stand-in, shared by everything in one test."""
    client = fakeredis.FakeRedis(decode_responses=True)
    redis_store.set_client(client)
    yield client
    redis_store.reset_client()


@pytest.fixture
def service(fake_client):
    """One KeyManagementService instance wired to the shared fake client."""
    return KeyManagementService()


@pytest.fixture(autouse=True)
def _clear_shared_key_manager():
    """
    The process-wide ``key_manager`` singleton (used by the public-key view
    and by common/security/e2e_encryption.py) is shared with every other test
    module in this process. Reset it before and after every test here so
    nothing leaks in either direction.
    """
    from infrastructure.keys import key_manager

    key_manager.reset()
    yield
    key_manager.reset()


# ---------------------------------------------------------------------------
# Test 1 -- neither key exists
# ---------------------------------------------------------------------------

def test_no_keys_generates_and_stores_both(service, fake_client):
    service.initialize()

    stored = redis_store.read_both()
    assert stored.public_key and stored.private_key
    assert service.get_public_key() == stored.public_key
    assert service.get_private_key() == stored.private_key


# ---------------------------------------------------------------------------
# Test 2 -- both keys exist and are valid
# ---------------------------------------------------------------------------

def test_existing_valid_pair_is_loaded_not_regenerated(service, fake_client):
    public_key, private_key = generate_keypair()
    redis_store.write_both(public_key, private_key)

    service.initialize()

    assert service.get_public_key() == public_key
    assert service.get_private_key() == private_key
    # Still exactly what was seeded -- nothing was regenerated over it.
    stored = redis_store.read_both()
    assert stored.public_key == public_key
    assert stored.private_key == private_key


# ---------------------------------------------------------------------------
# Test 3 -- only the public key exists
# ---------------------------------------------------------------------------

def test_public_only_fails_startup_without_replacing_anything(service, fake_client):
    public_key, _ = generate_keypair()
    fake_client.set(redis_store.PUBLIC_KEY_REDIS_KEY, public_key)

    with pytest.raises(KeyManagementError):
        service.initialize()

    # No replacement private key was silently generated.
    stored = redis_store.read_both()
    assert stored.public_key == public_key
    assert stored.private_key is None


# ---------------------------------------------------------------------------
# Test 4 -- only the private key exists (X25519 can safely re-derive)
# ---------------------------------------------------------------------------

def test_private_only_recovers_the_derived_public_key(service, fake_client):
    public_key, private_key = generate_keypair()
    fake_client.set(redis_store.PRIVATE_KEY_REDIS_KEY, private_key)

    service.initialize()

    assert service.get_public_key() == public_key
    assert service.get_private_key() == private_key
    # The derived public half was persisted, not just held in memory.
    stored = redis_store.read_both()
    assert stored.public_key == public_key


# ---------------------------------------------------------------------------
# Test 5 -- both exist but don't match
# ---------------------------------------------------------------------------

def test_mismatched_pair_fails_startup_and_leaves_redis_untouched(service, fake_client):
    public_a, _ = generate_keypair()
    _, private_b = generate_keypair()
    redis_store.write_both(public_a, private_b)

    with pytest.raises(KeyManagementError, match='inconsistent'):
        service.initialize()

    stored = redis_store.read_both()
    assert stored.public_key == public_a
    assert stored.private_key == private_b


# ---------------------------------------------------------------------------
# Test 6 -- Redis unavailable
# ---------------------------------------------------------------------------

def _unreachable_client():
    import redis as redis_lib

    # Nothing is listening on this port -- the connection attempt fails fast
    # rather than hanging for the usual multi-second default timeout.
    return redis_lib.Redis(
        host='127.0.0.1', port=1, decode_responses=True,
        socket_connect_timeout=0.2, socket_timeout=0.2,
    )


def test_redis_unavailable_fails_startup_in_production(service, settings):
    settings.DEBUG = False
    redis_store.set_client(_unreachable_client())

    with pytest.raises(KeyManagementError, match='Redis'):
        service.initialize()


def test_redis_unavailable_falls_back_to_ephemeral_key_in_debug(service, settings):
    settings.DEBUG = True
    redis_store.set_client(_unreachable_client())

    service.initialize()  # must not raise

    assert service.get_public_key()
    assert service.get_private_key()


# ---------------------------------------------------------------------------
# Test 7 -- two instances initializing simultaneously
# ---------------------------------------------------------------------------

def test_concurrent_initialization_converges_on_one_keypair(fake_client):
    # Two independent instances -- standing in for two application processes
    # booting at the same moment -- sharing only the fake Redis, not any
    # in-process state.
    instance_a = KeyManagementService()
    instance_b = KeyManagementService()
    results: dict[str, str] = {}
    errors: dict[str, Exception] = {}

    def run(name: str, svc: KeyManagementService) -> None:
        try:
            svc.initialize()
            results[name] = svc.get_public_key()
        except Exception as exc:  # noqa: BLE001 - captured for the assertion below
            errors[name] = exc

    threads = [
        threading.Thread(target=run, args=('a', instance_a)),
        threading.Thread(target=run, args=('b', instance_b)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, errors
    assert results['a'] == results['b']

    stored = redis_store.read_both()
    assert stored.public_key == results['a']


# ---------------------------------------------------------------------------
# Test 8 -- public-key endpoint
# ---------------------------------------------------------------------------

def test_public_key_endpoint_never_exposes_the_private_key(fake_client):
    from infrastructure.keys import key_manager

    key_manager.initialize()

    response = APIClient().get('/api/v1/crypto/public-key/')

    assert response.status_code == 200
    assert response.data['publicKey'] == key_manager.get_public_key()
    assert response.data['algorithm'] == 'X25519'
    assert 'privateKey' not in response.data
    assert key_manager.get_private_key() not in str(response.content)


def test_public_key_endpoint_returns_503_when_uninitialized():
    # _clear_shared_key_manager has already reset key_manager for this test;
    # nothing here calls initialize(), so the view has nothing to serve.
    response = APIClient().get('/api/v1/crypto/public-key/')

    assert response.status_code == 503
    assert 'publicKey' not in response.data


# ---------------------------------------------------------------------------
# Test 9 -- private key never appears in logs
# ---------------------------------------------------------------------------

def test_private_key_never_appears_in_logs(service, fake_client, caplog):
    with caplog.at_level(logging.DEBUG, logger='infrastructure.keys.service'):
        service.initialize()

    private_key = service.get_private_key()
    log_text = '\n'.join(record.getMessage() for record in caplog.records)
    assert private_key not in log_text


def test_private_key_never_appears_in_logs_on_mismatch(fake_client, caplog):
    public_a, _ = generate_keypair()
    _, private_b = generate_keypair()
    redis_store.write_both(public_a, private_b)

    with caplog.at_level(logging.DEBUG, logger='infrastructure.keys.service'):
        with pytest.raises(KeyManagementError):
            KeyManagementService().initialize()

    log_text = '\n'.join(record.getMessage() for record in caplog.records)
    assert private_b not in log_text


# ---------------------------------------------------------------------------
# Test 10 -- restart persistence
# ---------------------------------------------------------------------------

def test_public_key_survives_a_restart(fake_client):
    first_boot = KeyManagementService()
    first_boot.initialize()
    public_key_before = first_boot.get_public_key()

    # A restart is a brand new process: a new service instance, no shared
    # in-memory state, talking to the same (persistent) Redis.
    second_boot = KeyManagementService()
    second_boot.initialize()
    public_key_after = second_boot.get_public_key()

    assert public_key_before == public_key_after


# ---------------------------------------------------------------------------
# Integration: boot -> read endpoint -> "restart" -> read endpoint again
# ---------------------------------------------------------------------------

def test_endpoint_returns_the_same_public_key_across_a_restart(fake_client):
    from infrastructure.keys import key_manager

    client = APIClient()

    key_manager.initialize()
    first_response = client.get('/api/v1/crypto/public-key/')

    # Simulate a full process restart: forget everything in memory, then
    # boot again against the same (persistent) Redis.
    key_manager.reset()
    key_manager.initialize()
    second_response = client.get('/api/v1/crypto/public-key/')

    assert first_response.status_code == second_response.status_code == 200
    assert first_response.data['publicKey'] == second_response.data['publicKey']


# ---------------------------------------------------------------------------
# Validation edge cases
# ---------------------------------------------------------------------------

def test_malformed_stored_private_key_fails_startup(service, fake_client):
    public_key, _ = generate_keypair()
    fake_client.set(redis_store.PUBLIC_KEY_REDIS_KEY, public_key)
    fake_client.set(redis_store.PRIVATE_KEY_REDIS_KEY, 'not valid base64 !!!')

    with pytest.raises(KeyManagementError):
        service.initialize()


def test_wrong_length_stored_key_fails_startup(service, fake_client):
    public_key, _ = generate_keypair()
    fake_client.set(redis_store.PUBLIC_KEY_REDIS_KEY, public_key)
    fake_client.set(redis_store.PRIVATE_KEY_REDIS_KEY, base64.b64encode(b'too short').decode())

    with pytest.raises(KeyManagementError):
        service.initialize()


def test_get_public_key_before_initialize_raises(service):
    with pytest.raises(KeyManagementError, match='not been initialized'):
        service.get_public_key()


def test_initialize_is_idempotent_within_one_process(service, fake_client):
    service.initialize()
    first = service.get_public_key()

    # A second call must not touch Redis again or change anything.
    redis_store.reset_client()  # if this were re-read, it would now explode
    service.initialize()

    assert service.get_public_key() == first
