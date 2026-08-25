"""
Application identity keypair endpoints.

- GET /api/crypto/public-key/  -> the server's X25519 public key (anyone).

Mirrors api/views/push.py's push_public_key: a single AllowAny endpoint
handing out one public value, nothing else. The private key is never
reachable through this module -- the view only ever calls
KeyManagementService.get_public_key().
"""

from django.conf import settings
from django.http import Http404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common.security.e2e_encryption import (
    decrypt_payload,
    encrypt_payload,
    generate_keypair,
)
from infrastructure.keys import KeyManagementError, key_manager

ALGORITHM = 'X25519'


@api_view(['GET'])
@permission_classes([AllowAny])
def crypto_public_key(request):
    try:
        public_key = key_manager.get_public_key()
    except KeyManagementError:
        return Response(
            {'error': 'The cryptographic keypair is not currently available.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({'publicKey': public_key})


def _require_test_endpoints_enabled():
    if not getattr(settings, 'CRYPTO_TEST_ENDPOINTS_ENABLED', False):
        raise Http404


@api_view(['GET'])
@permission_classes([AllowAny])
def crypto_test_keypair(request):
    """
    A throwaway X25519 client keypair, plus the server key to encrypt toward.

    ``publicKey`` goes in the ``X-Client-Public-Key`` header of the real
    request; ``privateKey`` is what decrypts the response that comes back.
    A production client generates this itself and never transmits the private
    half -- there is no registration step, the key is asserted per request.
    """
    _require_test_endpoints_enabled()

    client_public, client_private = generate_keypair()
    try:
        server_public = key_manager.get_public_key()
    except KeyManagementError:
        return Response(
            {'error': 'The cryptographic keypair is not currently available.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {
            'publicKey': client_public,
            'privateKey': client_private,
            'serverPublicKey': server_public,
            'algorithm': ALGORITHM,
            'header': {'X-Client-Public-Key': client_public},
            'warning': (
                'Test helper. The private key is transmitted here, which a real '
                'client must never do.'
            ),
        }
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def crypto_test_encrypt(request):
    """
    Turn a plain payload into the ``{encrypted, nonce, checksum}`` envelope.

    Body::

        {"payload": {...}, "clientPrivateKey": "<optional>"}

    Omit ``clientPrivateKey`` and a fresh keypair is generated and returned
    alongside the envelope, so a single call yields everything one request
    needs. Supply one -- from ``/crypto/test/keypair/`` -- to keep the same
    identity across several calls and be able to decrypt each response.

    The response's ``body`` is what to send; ``header`` is what to send it
    with. Note the nonce is single-use for 24 hours: re-sending an identical
    body returns 409, not 400.
    """
    _require_test_endpoints_enabled()

    payload = request.data.get('payload')
    if not isinstance(payload, dict):
        return Response(
            {'error': 'Body must be {"payload": {...}} with payload a JSON object.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    client_private = request.data.get('clientPrivateKey')
    if client_private:
        # Derived rather than trusted separately, so the returned public key
        # always matches the private key actually used to encrypt.
        import nacl.public

        from common.security.e2e_encryption import _b64decode, _b64encode

        try:
            priv = nacl.public.PrivateKey(_b64decode(client_private, field='clientPrivateKey'))
        except Exception:
            return Response(
                {'error': 'clientPrivateKey is not a valid X25519 private key.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        client_public = _b64encode(bytes(priv.public_key))
    else:
        client_public, client_private = generate_keypair()

    try:
        server_public = key_manager.get_public_key()
    except KeyManagementError:
        return Response(
            {'error': 'The cryptographic keypair is not currently available.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    envelope = encrypt_payload(payload, server_public, client_private)

    return Response(
        {
            'header': {'X-Client-Public-Key': client_public},
            'body': envelope.to_dict(),
            'clientPublicKey': client_public,
            'clientPrivateKey': client_private,
            'serverPublicKey': server_public,
        }
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def crypto_test_decrypt(request):
    """
    Read an encrypted response back into plain JSON.

    Body::

        {"encrypted": "...", "nonce": "...", "checksum": "...",
         "clientPrivateKey": "..."}

    Encrypted endpoints encrypt their responses too, so without this a caller
    using Postman sees an unreadable envelope even when the request succeeded.

    Replay checking is deliberately off: this decrypts a response the server
    itself produced, and consuming the nonce here would poison the cache for a
    payload that was never a request.
    """
    _require_test_endpoints_enabled()

    missing = [
        f for f in ('encrypted', 'nonce', 'checksum', 'clientPrivateKey') if not request.data.get(f)
    ]
    if missing:
        return Response(
            {'error': f'Missing required field(s): {", ".join(missing)}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        server_public = key_manager.get_public_key()
    except KeyManagementError:
        return Response(
            {'error': 'The cryptographic keypair is not currently available.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    import json as _json

    from common.exceptions import DecryptionError

    try:
        plaintext = decrypt_payload(
            request.data['encrypted'],
            request.data['nonce'],
            server_public,
            request.data['checksum'],
            request.data['clientPrivateKey'],
            check_replay=False,
        )
    except DecryptionError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    try:
        decoded = _json.loads(plaintext)
    except ValueError:
        decoded = plaintext

    return Response({'decrypted': decoded})
