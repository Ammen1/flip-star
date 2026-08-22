"""
End-to-end encryption for sensitive payloads.

    from common.security import encrypt_payload, decrypt_payload

See ``e2e_encryption.py`` for the crypto design notes -- in short: X25519 +
NaCl box, same wire format as the reference Node.js implementation this was
ported from, with two upgrades: the server's keypair is Redis-backed and
managed automatically (see ``infrastructure/keys/``) instead of generated on
a timer and held in plaintext, and nonces are checked for replay.

See ``encrypted_transport.py`` for wiring this into actual DRF views --
``encrypted_endpoint`` / ``EncryptedPayloadMixin``.
"""

from common.security.client_ip import get_client_ip
from common.security.e2e_encryption import (
    EncryptedPayload,
    decrypt_payload,
    encrypt_payload,
    generate_keypair,
    get_server_private_key,
    get_server_public_key,
    reset_key_cache,
)
from common.security.encrypted_transport import (
    CLIENT_PUBLIC_KEY_HEADER_NAME,
    EncryptedJSONParser,
    EncryptedJSONRenderer,
    EncryptedPayloadMixin,
    encrypted_endpoint,
)
from common.security.pin_policy import is_pin_too_weak

__all__ = [
    'CLIENT_PUBLIC_KEY_HEADER_NAME',
    'EncryptedJSONParser',
    'EncryptedJSONRenderer',
    'EncryptedPayload',
    'EncryptedPayloadMixin',
    'decrypt_payload',
    'encrypt_payload',
    'encrypted_endpoint',
    'generate_keypair',
    'get_client_ip',
    'get_server_private_key',
    'get_server_public_key',
    'is_pin_too_weak',
    'reset_key_cache',
]
