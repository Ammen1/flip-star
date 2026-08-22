"""
End-to-end encryption for sensitive payloads.

Same primitive and wire format as the reference Node.js implementation this
was ported from: X25519 key agreement + XSalsa20-Poly1305 authenticated
encryption (NaCl's ``box`` construction, via PyNaCl here and tweetnacl there),
with a SHA-256 checksum of the plaintext carried alongside the ciphertext so a
receiver can confirm what it decrypted is what was meant, independent of the
box's own authentication tag.

Two changes from that reference, both closing real gaps:

1. **Key storage.** The reference stored the server's private key in Redis, in
   plaintext, generated fresh on a 24-hour timer with no validation that a
   restart didn't silently produce a different identity. The server's own
   keypair here is still Redis-resident (see ``infrastructure/keys``), but is
   generated once and persisted, validated on every load, protected against
   two instances racing to generate competing pairs at once, and never
   regenerated automatically over an existing key -- see
   ``infrastructure/keys/service.py`` for the full startup state machine.
   Access from this module goes through ``infrastructure.keys.key_manager``,
   which is initialized once per process at startup (``config/asgi.py`` /
   ``config/wsgi.py``) and cached in memory after that -- no Redis round trip
   per request.

2. **Replay protection.** The checksum authenticates *content*, not
   *freshness* -- an attacker who captures a valid encrypted message can
   resend the exact same bytes later and it will decrypt and checksum-verify
   identically. ``decrypt_payload`` additionally tracks each nonce it has
   seen in the cache for :data:`NONCE_REPLAY_WINDOW_SECONDS` and rejects a
   repeat. NaCl nonces are meant to be unique per message in the first place,
   so seeing one twice is itself a signal, not just an accounting device.

Performance: NaCl box operations run in low single-digit microseconds for
payloads of this size -- the cost here is dominated by the cache round trip
for the replay check, which is the same Redis-backed cache every other
request already uses in production, not additional infrastructure.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import nacl.exceptions
import nacl.public
import nacl.utils
from django.core.cache import cache

from common.exceptions import DecryptionError, ReplayDetected
from infrastructure.keys import key_manager

#: How long a nonce is remembered for replay detection. Generous relative to
#: any plausible legitimate retry window (network retries, at-least-once
#: delivery from a queue) while still bounding cache growth.
NONCE_REPLAY_WINDOW_SECONDS = 24 * 60 * 60

#: Cache key prefix for seen nonces. Namespaced so a cache flush pattern or a
#: key inspection immediately identifies what these entries are for.
_NONCE_CACHE_PREFIX = 'e2e:nonce:'

_BASE64_RE = re.compile(r'^[A-Za-z0-9+/]+={0,2}$')


def _is_valid_base64(value: str) -> bool:
    return bool(value) and bool(_BASE64_RE.match(value))


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode('ascii')


def _b64decode(value: str, *, field: str) -> bytes:
    if not _is_valid_base64(value):
        raise DecryptionError(f'{field} is not valid base64.')
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise DecryptionError(f'{field} could not be decoded.') from exc


def _checksum(plaintext: str) -> str:
    """SHA-256 of the plaintext payload, hex-encoded."""
    return hashlib.sha256(plaintext.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class EncryptedPayload:
    """The three values a receiver needs to decrypt and verify a message."""

    encrypted: str
    nonce: str
    checksum: str

    def to_dict(self) -> dict[str, str]:
        return {'encrypted': self.encrypted, 'nonce': self.nonce, 'checksum': self.checksum}


def encrypt_payload(
    data: dict[str, Any],
    receiver_public_key_b64: str,
    sender_private_key_b64: str,
) -> EncryptedPayload:
    """
    Encrypt ``data`` for a specific receiver, authenticated as a specific sender.

    ``data`` is serialised with ``json.dumps`` before encryption, so it must be
    JSON-serialisable. Matches the reference implementation's wire format
    exactly: a receiver decodes with the mirroring ``decrypt_payload`` (or the
    original ``decryptData`` in the Node.js service) regardless of which side
    encrypted.

    Raises:
        DecryptionError: if either key is not valid base64 or the wrong length
            for an X25519 key. Reused here rather than a separate exception
            because the failure mode -- "this key material is unusable" -- is
            the same one a bad decrypt raises.
    """
    receiver_key_bytes = _b64decode(receiver_public_key_b64, field='receiver_public_key')
    sender_key_bytes = _b64decode(sender_private_key_b64, field='sender_private_key')

    try:
        receiver_public_key = nacl.public.PublicKey(receiver_key_bytes)
        sender_private_key = nacl.public.PrivateKey(sender_key_bytes)
    except (nacl.exceptions.CryptoError, ValueError, TypeError) as exc:
        raise DecryptionError('One or more keys are malformed.') from exc

    plaintext = json.dumps(data, separators=(',', ':'), sort_keys=True)
    checksum = _checksum(plaintext)

    box = nacl.public.Box(sender_private_key, receiver_public_key)
    nonce = nacl.utils.random(nacl.public.Box.NONCE_SIZE)
    ciphertext = box.encrypt(plaintext.encode('utf-8'), nonce).ciphertext

    return EncryptedPayload(
        encrypted=_b64encode(ciphertext),
        nonce=_b64encode(nonce),
        checksum=checksum,
    )


def decrypt_payload(
    encrypted_b64: str,
    nonce_b64: str,
    sender_public_key_b64: str,
    expected_checksum: str,
    receiver_private_key_b64: str,
    *,
    check_replay: bool = True,
) -> str:
    """
    Decrypt and verify a payload produced by :func:`encrypt_payload`.

    Returns the decrypted plaintext (a JSON string -- callers that expect an
    object should ``json.loads`` it themselves, matching the reference
    implementation's contract of returning text, not a parsed object).

    Verification order matters: base64 decoding, then the box's own
    authentication (which catches tampering and wrong keys), then the replay
    check, then the checksum. Each stage raises before touching data that
    depends on the previous stage having succeeded.

    Raises:
        DecryptionError: base64 is invalid, keys are malformed, the box fails
            to authenticate, or the checksum doesn't match. The exception
            message is deliberately generic in all these cases -- see the
            module docstring on why.
        ReplayDetected: this nonce has been seen before within the replay
            window. Only raised when ``check_replay`` is True (the default);
            pass False for pure verification with no side effect on the nonce
            cache, e.g. when re-validating a payload that was already
            accepted.
    """
    encrypted = _b64decode(encrypted_b64, field='encrypted')
    nonce = _b64decode(nonce_b64, field='nonce')
    sender_key_bytes = _b64decode(sender_public_key_b64, field='sender_public_key')
    receiver_key_bytes = _b64decode(receiver_private_key_b64, field='receiver_private_key')

    try:
        sender_public_key = nacl.public.PublicKey(sender_key_bytes)
        receiver_private_key = nacl.public.PrivateKey(receiver_key_bytes)
    except (nacl.exceptions.CryptoError, ValueError, TypeError) as exc:
        raise DecryptionError('One or more keys are malformed.') from exc

    box = nacl.public.Box(receiver_private_key, sender_public_key)
    try:
        plaintext_bytes = box.decrypt(encrypted, nonce)
    except nacl.exceptions.CryptoError as exc:
        raise DecryptionError('Payload failed authentication.') from exc

    if check_replay and _nonce_already_seen(nonce_b64):
        raise ReplayDetected()

    plaintext = plaintext_bytes.decode('utf-8')

    if _checksum(plaintext) != expected_checksum:
        raise DecryptionError('Checksum does not match decrypted content.')

    return plaintext


def _nonce_already_seen(nonce_b64: str) -> bool:
    """
    Atomically check-and-record a nonce. True if it was already recorded.

    ``cache.add`` only writes when the key is absent, and reports whether it
    wrote -- so this is a single round trip with no separate check-then-set
    race between concurrent requests carrying the same nonce.
    """
    key = _NONCE_CACHE_PREFIX + nonce_b64
    newly_recorded = cache.add(key, True, timeout=NONCE_REPLAY_WINDOW_SECONDS)
    return not newly_recorded


# ---------------------------------------------------------------------------
# Server key pair
# ---------------------------------------------------------------------------
# The server's own identity keypair lives in Redis and is owned by
# infrastructure.keys.key_manager -- initialized once at process startup
# (config/asgi.py / config/wsgi.py), validated, and cached in memory from
# then on, so these are plain delegations with no per-request Redis cost.
# See infrastructure/keys/service.py for the startup state machine.


def get_server_public_key() -> str:
    """The server's own public key, base64-encoded. Safe to hand out freely."""
    return key_manager.get_public_key()


def get_server_private_key() -> str:
    """The server's own private key, base64-encoded. Never log or return this."""
    return key_manager.get_private_key()


def reset_key_cache() -> None:
    """Test-only: forget the in-memory keypair so the next access re-reads
    Redis. Delegates to the KeyManagementService singleton."""
    key_manager.reset()


def generate_keypair() -> tuple[str, str]:
    """
    Generate a fresh, ad-hoc X25519 key pair. Returns ``(public_key_b64,
    private_key_b64)``.

    For making arbitrary counterparty keys (tests, a client generating its
    own pair) -- not for the server's own identity, which
    ``infrastructure.keys.generate_keypair`` produces and Redis persists.
    """
    private_key = nacl.public.PrivateKey.generate()
    public_key = private_key.public_key
    return _b64encode(bytes(public_key)), _b64encode(bytes(private_key))
