"""
Raw Redis operations backing the application's identity keypair.

No crypto validation lives here -- that is ``infrastructure/keys/service.py``'s
job. This module only knows how to read, atomically write, and lock around a
fixed pair of Redis keys. Kept deliberately dumb so it is easy to point at a
fake client in tests without dragging crypto or Django app-registry concerns
along with it.

Storage lives on a Redis logical DB separate from the cache (1) and Celery
broker (0) -- see ``settings.REDIS_CRYPTO_URL`` -- specifically so an
operational cache flush cannot take the keypair down with it.
"""

from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

import redis
from django.conf import settings

from infrastructure.keys.exceptions import KeyManagementError

#: Namespaced so these keys cannot collide with another application sharing
#: the same Redis instance -- deliberately not a generic name like
#: "publicKey" or "key".
_NAMESPACE = 'flipstar:crypto'
PUBLIC_KEY_REDIS_KEY = f'{_NAMESPACE}:public_key'
PRIVATE_KEY_REDIS_KEY = f'{_NAMESPACE}:private_key'
_INIT_LOCK_KEY = f'{_NAMESPACE}:init_lock'

#: Generous relative to how long generating and storing a keypair actually
#: takes (microseconds) -- this only needs to outlast a slow Redis round trip,
#: not bound normal operation.
_LOCK_TTL_MS = 30_000
_LOCK_POLL_INTERVAL_S = 0.05
_LOCK_WAIT_TIMEOUT_S = 10


@dataclass(frozen=True)
class StoredKeyPair:
    public_key: str | None
    private_key: str | None


_client: redis.Redis | None = None
_client_lock = threading.Lock()


#: Bounds how long startup can hang trying to reach a genuinely unreachable
#: Redis, in either the fail-fast production path or the DEBUG fallback path
#: (see KeyManagementService.initialize) -- without this, a dropped-packet
#: style outage falls back to the OS's own TCP connect timeout, which can be
#: tens of seconds.
_CONNECT_TIMEOUT_S = 5


def get_client() -> redis.Redis:
    """The shared Redis client for keypair storage, built once per process."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = redis.Redis.from_url(
                settings.REDIS_CRYPTO_URL,
                decode_responses=True,
                socket_connect_timeout=_CONNECT_TIMEOUT_S,
            )
    return _client


def set_client(client: redis.Redis) -> None:
    """Test-only: inject a fake/alternate client (e.g. ``fakeredis``)."""
    global _client
    _client = client


def reset_client() -> None:
    """Test-only: forget the cached client so the next ``get_client()`` call
    rebuilds it from settings."""
    global _client
    _client = None


def read_both() -> StoredKeyPair:
    client = get_client()
    public_key, private_key = client.mget([PUBLIC_KEY_REDIS_KEY, PRIVATE_KEY_REDIS_KEY])
    return StoredKeyPair(public_key=public_key, private_key=private_key)


def write_both(public_key: str, private_key: str) -> None:
    """
    Atomically store both halves of a keypair.

    A transaction (MULTI/EXEC) pipeline ensures a crash between the two
    writes can never leave a reader observing only one half -- the exact
    "only one key exists" state the startup state machine treats as a fatal
    key-management error.
    """
    client = get_client()
    with client.pipeline(transaction=True) as pipe:
        pipe.set(PUBLIC_KEY_REDIS_KEY, public_key)
        pipe.set(PRIVATE_KEY_REDIS_KEY, private_key)
        pipe.execute()


def write_public_only(public_key: str) -> None:
    """Used only to persist a public key re-derived from a surviving private
    key (the one half-missing case X25519 can safely recover from)."""
    get_client().set(PUBLIC_KEY_REDIS_KEY, public_key)


def overwrite_both(public_key: str, private_key: str) -> None:
    """
    Unconditionally replace both halves -- used only by the explicit,
    operator-triggered rotation command, never by startup initialization.
    Startup only ever fills in what's missing; it must never call this.
    """
    write_both(public_key, private_key)


@contextmanager
def init_lock():
    """
    Distributed lock guarding keypair initialization, so two instances
    booting at the same moment cannot both observe "nothing exists" and each
    generate a different keypair.

    Acquire is a plain ``SET NX PX`` (no Lua). Release is a WATCH/MULTI/EXEC
    compare-and-delete, also without Lua/EVAL -- unlike redis-py's built-in
    ``Redis.lock()``, whose release path requires script support. Nothing
    else in this project's Redis usage depends on scripting, and this keeps
    the lock testable against a plain in-memory fake with no native
    dependencies.
    """
    client = get_client()
    token = uuid.uuid4().hex
    deadline = time.monotonic() + _LOCK_WAIT_TIMEOUT_S
    acquired = False
    while time.monotonic() < deadline:
        if client.set(_INIT_LOCK_KEY, token, nx=True, px=_LOCK_TTL_MS):
            acquired = True
            break
        time.sleep(_LOCK_POLL_INTERVAL_S)

    if not acquired:
        raise KeyManagementError(
            f'Timed out after {_LOCK_WAIT_TIMEOUT_S}s waiting for the keypair '
            'initialization lock. Another instance may be stuck mid-initialization.'
        )

    try:
        yield
    finally:
        with client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(_INIT_LOCK_KEY)
                    current = pipe.get(_INIT_LOCK_KEY)
                    pipe.multi()
                    if current == token:
                        pipe.delete(_INIT_LOCK_KEY)
                    pipe.execute()
                    break
                except redis.WatchError:
                    continue
