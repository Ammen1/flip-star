"""
Application identity keypair endpoints.

- GET /api/crypto/public-key/  -> the server's X25519 public key (anyone).

Mirrors api/views/push.py's push_public_key: a single AllowAny endpoint
handing out one public value, nothing else. The private key is never
reachable through this module -- the view only ever calls
KeyManagementService.get_public_key().
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from infrastructure.keys import KeyManagementError, key_manager

ALGORITHM = 'X25519'


@api_view(['GET'])
@permission_classes([AllowAny])
def crypto_public_key(request):
    try:
        public_key = key_manager.get_public_key()
    except KeyManagementError:
        # Key initialization failed at startup or hasn't completed -- a
        # server-side condition, not anything the caller did wrong.
        return Response(
            {'error': 'The cryptographic keypair is not currently available.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({'publicKey': public_key, 'algorithm': ALGORITHM})
