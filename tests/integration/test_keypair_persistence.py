"""Blocker B-03 / §5.4: the E2E server keypair must not be silently replaced.

The keypair lives in Redis DB 2, deliberately isolated from the cache so an
operational `FLUSHDB` cannot destroy it. What that isolation does *not* survive
is the whole instance losing its data — which a pod reschedule does, and which
`H-05-redis-failure-test.txt` measured.

The consequence matters because of how the loss is handled: the state machine in
`infrastructure/keys/service.py` treats "neither key exists" as *generate a new
pair*. The server then holds a key nobody's open session sealed to, and
`Flipstar-web/crypto.js` fetches the server key once per page load and keeps it
in memory — so every live session's requests fail, silently, until a reload.

These tests pin the contract that keeps the blast radius to that and no worse:

* an existing pair is **loaded, never regenerated**
* a private-only store **derives** the public half rather than minting a new pair
* a public-only store **fails loudly** rather than inventing a private key that
  silently invalidates a public one someone else may already hold

The last is the important one. If that ever became "generate a replacement", a
partial data loss would look like a successful start while breaking every client
permanently rather than until a reload.
"""

import pytest

pytestmark = [pytest.mark.integration]


@pytest.fixture
def key_store():
    """A fresh in-memory key store, isolated per test."""
    import fakeredis

    from infrastructure.keys import key_manager, redis_store

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    try:
        yield redis_store
    finally:
        key_manager.reset()
        redis_store.reset_client()


def _stored(store):
    pair = store.read_both()
    return pair.public_key, pair.private_key


# ── the pair is stable across restarts ───────────────────────────────────────


def test_an_existing_keypair_is_loaded_not_regenerated(key_store):
    """The whole point: a restart must not change the server's identity."""
    from infrastructure.keys import key_manager

    key_manager.initialize()
    first_public, first_private = _stored(key_store)
    assert first_public and first_private

    # Simulate a process restart: drop the in-memory cache, keep the store.
    key_manager.reset()
    key_manager.initialize()

    second_public, second_private = _stored(key_store)
    assert second_public == first_public, 'the public key changed across a restart'
    assert second_private == first_private, 'the private key changed across a restart'


def test_the_public_key_served_matches_what_is_stored(key_store):
    from infrastructure.keys import key_manager

    key_manager.initialize()
    stored_public, _ = _stored(key_store)
    assert key_manager.get_public_key() == stored_public


def test_an_empty_store_generates_exactly_one_pair(key_store):
    """This is the reschedule case, and it is why a Redis wipe breaks sessions."""
    from infrastructure.keys import key_manager

    assert _stored(key_store) == (None, None)
    key_manager.initialize()
    public, private = _stored(key_store)
    assert public and private


def test_a_wipe_produces_a_different_key_which_is_the_documented_cost(key_store):
    """Not a bug — the recorded consequence. Pinned so it cannot worsen silently."""
    from infrastructure.keys import key_manager, redis_store

    key_manager.initialize()
    original_public, _ = _stored(key_store)

    # What a pod reschedule does to an emptyDir-backed Redis.
    client = redis_store.get_client()
    client.delete(redis_store.PUBLIC_KEY_REDIS_KEY, redis_store.PRIVATE_KEY_REDIS_KEY)
    key_manager.reset()
    key_manager.initialize()

    new_public, _ = _stored(key_store)
    assert new_public != original_public, (
        'a wiped store must produce a new key — if this ever passed by returning '
        'the old one, something is caching the keypair outside Redis'
    )


# ── partial loss must not mint a replacement private key ─────────────────────


def test_a_private_only_store_derives_the_public_half(key_store):
    """X25519 makes this safe: the public key is a function of the private one."""
    from infrastructure.keys import key_manager, redis_store

    key_manager.initialize()
    original_public, original_private = _stored(key_store)

    redis_store.get_client().delete(redis_store.PUBLIC_KEY_REDIS_KEY)
    key_manager.reset()
    key_manager.initialize()

    recovered_public, recovered_private = _stored(key_store)
    assert recovered_private == original_private, 'the private key must be untouched'
    assert recovered_public == original_public, (
        'the public half must be DERIVED from the surviving private key, not '
        'replaced — deriving it keeps every existing client working'
    )


def test_a_public_only_store_refuses_to_start(key_store):
    """The load-bearing one.

    A surviving public key may already be held by clients. Minting a fresh
    private key to pair with it would invalidate them *permanently* and look like
    a clean startup. Refusing is the correct, louder outcome.
    """
    from infrastructure.keys import key_manager, redis_store

    key_manager.initialize()
    _original_public, original_private = _stored(key_store)

    redis_store.get_client().delete(redis_store.PRIVATE_KEY_REDIS_KEY)
    key_manager.reset()

    with pytest.raises(Exception) as exc:
        key_manager.initialize()

    message = str(exc.value).lower()
    assert (
        'private' in message or 'public' in message
    ), f'the failure should name the key problem; got: {exc.value!r}'

    # And it must not have written a replacement on the way out.
    _, private_after = _stored(key_store)
    assert (
        private_after is None
    ), 'initialize() must not mint a private key for an orphaned public one'
    assert original_private is not None


def test_a_mismatched_pair_refuses_to_start(key_store):
    """Two valid keys that are not each other's counterpart."""
    from infrastructure.keys import key_manager, redis_store
    from infrastructure.keys.service import generate_keypair

    first_public, _first_private = generate_keypair()
    _second_public, second_private = generate_keypair()
    redis_store.overwrite_both(first_public, second_private)
    key_manager.reset()

    # Deliberately broad: the service raises its own exception type here and the
    # point of the test is that it refuses at all, not which class it picks.
    # Narrowed only to exclude the two that would mean the test itself is wrong.
    with pytest.raises(Exception) as exc:  # noqa: B017
        key_manager.initialize()
    assert not isinstance(exc.value, AssertionError | ImportError)


def test_initialize_is_idempotent_within_a_process(key_store):
    """Called from both config/asgi.py and config/wsgi.py."""
    from infrastructure.keys import key_manager

    key_manager.initialize()
    public = key_manager.get_public_key()
    key_manager.initialize()
    key_manager.initialize()
    assert key_manager.get_public_key() == public
