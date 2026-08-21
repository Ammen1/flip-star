"""
Redis-backed persistence for the application's own cryptographic identity
keypair (X25519).

    from infrastructure.keys import key_manager
    key_manager.get_public_key()

See ``service.py`` for the full startup state machine and design notes.
``common/security/e2e_encryption.py`` is what actually uses this keypair to
encrypt/decrypt payloads; this package only owns where it lives and how it
gets there.
"""

from infrastructure.keys.exceptions import KeyManagementError
from infrastructure.keys.service import KeyManagementService, generate_keypair, key_manager

__all__ = ['KeyManagementError', 'KeyManagementService', 'generate_keypair', 'key_manager']
