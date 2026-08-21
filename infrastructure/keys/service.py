"""
``KeyManagementService``: the application's own X25519 identity keypair.

Algorithm
    X25519 (Curve25519 ECDH) -- the same primitive already used for payload
    encryption in ``common/security/e2e_encryption.py``, which is what
    actually uses this keypair (as the receiver's half when decrypting
    inbound payloads, and the sender's half when encrypting outbound ones).
    Chosen for compatibility with the Node.js reference implementation this
    was ported from, not chosen arbitrarily here.
Key format
    Private key: raw 32-byte X25519 scalar.
    Public key: raw 32-byte X25519 point (the scalar's basepoint multiple).
Encoding
    Standard base64, ASCII text -- one Redis string per half.
Storage format
    Two plain Redis string keys (see ``infrastructure/keys/redis_store.py``),
    not a serialized blob, so each half can independently exist, be missing,
    or be inspected without decoding the other.

A note on X25519 specifically: a public key is *always* a deterministic
function of the private key (scalar multiplication with the base point) --
there is no independent public value the way there would be with, say, RSA's
modulus. That is what makes it safe to recover a missing public half from a
surviving private half (state ``has_private and not has_public`` below): it
is not a special-case hack, it is the same computation used to validate that
a stored pair matches in the first place.

State machine run under ``infrastructure.keys.redis_store.init_lock()`` at
startup:

    both exist, valid        -> load and use them
    neither exists            -> generate, store atomically, use them
    private exists, public
      does not                -> derive the public half (safe for X25519,
                                  see above), persist it, use the pair
    public exists, private
      does not                -> FAIL. The public half may already be known
                                  to another party; generating a replacement
                                  private key would silently invalidate it.
    both exist, mismatched    -> FAIL. Redis is left untouched -- this
                                  service only ever *adds* a value that was
                                  missing, never overwrites one that already
                                  has a value (rotation is a separate,
                                  explicit administrative operation; see
                                  ``manage.py rotate_crypto_keypair``).
"""

from __future__ import annotations

import base64
import binascii
import logging
import threading

import nacl.exceptions
import nacl.public
import redis

from infrastructure.keys import redis_store
from infrastructure.keys.exceptions import KeyManagementError

logger = logging.getLogger(__name__)

_RAW_KEY_LENGTH = 32  # bytes, for X25519


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode('ascii')


def _decode_key(value: str, *, label: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise KeyManagementError(f'Stored {label} is not valid base64.') from exc
    if len(raw) != _RAW_KEY_LENGTH:
        raise KeyManagementError(f'Stored {label} is not a {_RAW_KEY_LENGTH}-byte X25519 key.')
    return raw


def _derive_public(private_raw: bytes) -> bytes:
    return bytes(nacl.public.PrivateKey(private_raw).public_key)


def generate_keypair() -> tuple[str, str]:
    """Generate a fresh X25519 key pair. Returns ``(public_key_b64, private_key_b64)``."""
    private_key = nacl.public.PrivateKey.generate()
    public_key = private_key.public_key
    return _b64encode(bytes(public_key)), _b64encode(bytes(private_key))


class KeyManagementService:
    """
    Owns the application's identity keypair: startup initialization,
    validation, and in-memory access afterwards.

    Controllers/serializers must only ever call ``get_public_key()``.
    ``get_private_key()`` is for internal cryptographic code (currently just
    ``common/security/e2e_encryption.py``) -- never pass its return value to
    a serializer, a log call, or an exception message.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._public_key: str | None = None
        self._private_key: str | None = None
        self._initialized = False

    def initialize(self) -> None:
        """
        Idempotent and safe to call from more than one entry point in the
        same process (both ``config/asgi.py`` and ``config/wsgi.py`` call
        this) -- once a key pair is cached in memory, later calls are a
        no-op rather than a repeat Redis round trip.

        If Redis is unreachable, behavior depends on ``settings.DEBUG``:
        production (``DEBUG=False``) fails startup, since a keypair that
        silently differs between restarts is a worse outcome than the
        process refusing to start. Local development (``DEBUG=True``) falls
        back to a one-off in-memory keypair instead -- the same convenience
        ``USE_LOCMEM_CACHE`` already gives the cache and channel layer (see
        ``config/settings/development.py``), so a developer without Redis
        running isn't forced to stand one up just to boot the server. That
        fallback key is never persisted and does not survive a restart --
        entirely unlike the real, Redis-backed keypair.
        """
        with self._lock:
            if self._initialized:
                return

            logger.info('Initializing cryptographic keypair...')
            try:
                with redis_store.init_lock():
                    # Re-read *under the lock*: another process may have
                    # finished generating the keypair while this one was
                    # waiting for the lock, which turns this into the
                    # "both exist" load-and-validate path below instead of a
                    # second, competing generation.
                    public_key, private_key = self._load_and_reconcile()
            except KeyManagementError:
                logger.error('Failed to initialize cryptographic keypair.')
                raise
            except redis.exceptions.RedisError as exc:
                from django.conf import settings

                if settings.DEBUG:
                    logger.warning(
                        'Redis unavailable; falling back to a temporary, '
                        'in-memory-only keypair for local development. This '
                        'key will NOT survive a restart and is never used '
                        'when DEBUG is False.'
                    )
                    public_key, private_key = generate_keypair()
                else:
                    logger.error('Failed to initialize cryptographic keypair: Redis unavailable.')
                    raise KeyManagementError(
                        'Could not reach Redis to initialize the cryptographic keypair. '
                        'Startup aborted.'
                    ) from exc

            self._public_key = public_key
            self._private_key = private_key
            self._initialized = True
            logger.info('Cryptographic keypair loaded successfully from Redis.')

    def _load_and_reconcile(self) -> tuple[str, str]:
        stored = redis_store.read_both()
        has_public = bool(stored.public_key)
        has_private = bool(stored.private_key)

        if has_public and has_private:
            self._validate_pair(stored.public_key, stored.private_key)
            logger.info('Existing cryptographic keypair found and validated.')
            return stored.public_key, stored.private_key

        if not has_public and not has_private:
            logger.info('No keypair found; generating new keypair.')
            public_key, private_key = generate_keypair()
            redis_store.write_both(public_key, private_key)
            logger.info('Cryptographic keypair generated and stored successfully.')
            return public_key, private_key

        if has_private and not has_public:
            logger.warning(
                'Public key missing from Redis but private key present; '
                'deriving the public key from the stored private key.'
            )
            private_raw = _decode_key(stored.private_key, label='private key')
            public_key = _b64encode(_derive_public(private_raw))
            redis_store.write_public_only(public_key)
            return public_key, stored.private_key

        # has_public and not has_private: the one state that can never be
        # safely repaired automatically -- the public half may already be in
        # a counterparty's hands, so generating a fresh private key would
        # silently produce a pair the outside world doesn't recognize.
        logger.error(
            'Private key missing from Redis but public key present. '
            'Cannot safely recover -- startup aborted.'
        )
        raise KeyManagementError(
            'Public key exists in Redis but the private key does not. Refusing '
            'to generate a replacement keypair, since that would invalidate the '
            'public key already in circulation. Restore the private key from '
            'backup, or clear both Redis keys to allow a fresh pair to be '
            f'generated (redis-cli DEL {redis_store.PUBLIC_KEY_REDIS_KEY}).'
        )

    def _validate_pair(self, public_key_b64: str, private_key_b64: str) -> None:
        public_raw = _decode_key(public_key_b64, label='public key')
        private_raw = _decode_key(private_key_b64, label='private key')

        try:
            derived_public = _derive_public(private_raw)
        except (nacl.exceptions.CryptoError, ValueError, TypeError) as exc:
            logger.error('Stored cryptographic keypair is invalid.')
            raise KeyManagementError('Stored private key is malformed.') from exc

        if derived_public != public_raw:
            logger.error('Stored public/private keys do not match.')
            raise KeyManagementError(
                'Cryptographic keypair in Redis is inconsistent. Startup aborted.'
            )

    def get_public_key(self) -> str:
        """The server's own public key, base64-encoded. Safe to hand out freely."""
        self._require_initialized()
        return self._public_key

    def get_private_key(self) -> str:
        """
        INTERNAL ONLY. For cryptographic code that needs to act as this
        server (see ``common/security/e2e_encryption.py``). Never expose
        this through a serializer, a log call, or an exception message.
        """
        self._require_initialized()
        return self._private_key

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise KeyManagementError(
                'Cryptographic keypair has not been initialized. '
                'KeyManagementService.initialize() must run at application '
                'startup before any code reads the keypair.'
            )

    def reset(self) -> None:
        """Test-only: forget the in-memory keypair so the next
        ``initialize()`` call re-reads Redis from scratch."""
        with self._lock:
            self._public_key = None
            self._private_key = None
            self._initialized = False


#: Process-wide singleton shared by config/asgi.py, config/wsgi.py, the
#: public-key view, and common/security/e2e_encryption.py.
key_manager = KeyManagementService()
