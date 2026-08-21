"""
DRF integration for the encrypted request/response pattern.

Wires ``common/security/e2e_encryption.py``'s ``encrypt_payload``/
``decrypt_payload`` into the actual HTTP request/response cycle for
opted-in views:

    client -> encrypted request -> Django auth -> permissions ->
    decrypt -> serializer validation -> view -> encrypt response -> client

DRF has no per-route middleware chain the way the Express reference this was
modeled on does. It doesn't need one here: DRF's own request/response
boundary already sits at exactly the two points the flow needs. A custom
Parser decrypts ``request.data`` before a serializer ever sees it; a custom
Renderer encrypts the response body after the view returns. Parsing is lazy
(DRF only parses when a view/serializer touches ``request.data``) and runs
inside the same exception-handled ``dispatch()`` as everything else, so a
``DecryptionError``/``ReplayDetected`` raised here reaches the client as a
normal 400/409 through the existing
``common.exceptions.handlers.api_exception_handler`` -- no new error
handling was added for this.

Rendering is a different story and the reason this module does NOT simply
raise from the renderer on a missing key: DRF's response rendering happens
lazily, outside ``dispatch()``'s try/except, when Django serializes the
response body. An exception raised there either surfaces as a raw,
unhandled 500 or -- worse -- runs *after* the view's business logic already
executed a side effect (a wallet debit, a mandate creation) that the caller
then never learns the outcome of. So every entry point into this module
validates the client's public key up front and fails closed with
``DecryptionError`` (400) *before* the view body runs at all, for every HTTP
method -- not only ones with a body.

Wire format
-----------
Request body (POST/PUT/PATCH): exactly ``EncryptedPayload.to_dict()`` --
``{"encrypted": ..., "nonce": ..., "checksum": ...}``. Response body: the
same shape, produced by encrypting the view's normal JSON output.

The client's own public key is deliberately *not* part of that envelope --
it travels in the ``X-Client-Public-Key`` header on every request, so it is
available independent of whether the request has a body at all (a GET
request has nothing to decrypt, but its response is still encrypted back to
the caller). This project has no per-user client-key registry: the client
asserts its public key on every request rather than registering it once.

Opting a view in
-----------------
Function-based views (apply *below* ``@api_view`` so DRF reads the
parser/renderer classes this decorator sets)::

    @api_view(['POST'])
    @encrypted_endpoint
    def my_view(request):
        ...

Class-based views/ViewSets::

    class MyView(EncryptedPayloadMixin, APIView):
        ...
"""

from __future__ import annotations

import json
import logging
from functools import wraps

from django.conf import settings
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer

from common.exceptions import DecryptionError
from common.security.e2e_encryption import decrypt_payload, encrypt_payload, get_server_private_key

logger = logging.getLogger(__name__)

#: The client's public key travels on this header on every request to an
#: encrypted endpoint. ``META`` key form (Django's ``HTTP_`` + uppercase +
#: underscore transform) and the human-readable form used in error messages
#: and by callers setting the header.
CLIENT_PUBLIC_KEY_META_KEY = 'HTTP_X_CLIENT_PUBLIC_KEY'
CLIENT_PUBLIC_KEY_HEADER_NAME = 'X-Client-Public-Key'

_REQUIRED_ENVELOPE_FIELDS = {'encrypted', 'nonce', 'checksum'}


def _client_public_key(request) -> str | None:
    if request is None:
        return None
    return request.META.get(CLIENT_PUBLIC_KEY_META_KEY)


def require_client_public_key(request) -> str:
    """The caller's public key, or a 400 ``DecryptionError`` if absent."""
    client_public_key = _client_public_key(request)
    if not client_public_key:
        raise DecryptionError(
            f'Missing required {CLIENT_PUBLIC_KEY_HEADER_NAME} header.'
        )
    return client_public_key


class EncryptedJSONParser(JSONParser):
    """Decrypts an ``EncryptedPayload``-shaped JSON body into ``request.data``."""

    media_type = 'application/json'

    def parse(self, stream, media_type=None, parser_context=None):
        parser_context = parser_context or {}
        request = parser_context.get('request')
        encoding = parser_context.get('encoding', settings.DEFAULT_CHARSET)

        raw = stream.read()
        if not raw:
            return {}

        try:
            envelope = json.loads(raw.decode(encoding))
        except (ValueError, UnicodeDecodeError, LookupError) as exc:
            raise DecryptionError('Encrypted request body is not valid JSON.') from exc

        if not isinstance(envelope, dict) or not _REQUIRED_ENVELOPE_FIELDS <= envelope.keys():
            raise DecryptionError(
                'Encrypted request body must contain "encrypted", "nonce" and "checksum".'
            )

        client_public_key = require_client_public_key(request)

        plaintext = decrypt_payload(
            envelope['encrypted'], envelope['nonce'], client_public_key,
            envelope['checksum'], get_server_private_key(),
        )
        try:
            return json.loads(plaintext)
        except ValueError as exc:
            raise DecryptionError('Decrypted request body is not valid JSON.') from exc


class EncryptedJSONRenderer(JSONRenderer):
    """Encrypts the response body to the caller's public key from ``X-Client-Public-Key``."""

    media_type = 'application/json'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            # Matches JSONRenderer's own early return (e.g. 204 responses) --
            # nothing to encrypt.
            return b''

        renderer_context = renderer_context or {}
        request = renderer_context.get('request')
        client_public_key = _client_public_key(request)

        if not client_public_key:
            # Reachable only if this renderer is attached without going
            # through encrypted_endpoint / EncryptedPayloadMixin (both
            # reject the request before this point if the header is
            # missing). Rendering plain rather than raising matters here
            # specifically: see the module docstring on why raising from a
            # renderer is unsafe.
            logger.warning(
                'EncryptedJSONRenderer used without a client public key; '
                'rendering unencrypted. This should not happen on a view '
                'that uses encrypted_endpoint or EncryptedPayloadMixin.'
            )
            return super().render(data, accepted_media_type, renderer_context)

        sealed = encrypt_payload(
            data,
            receiver_public_key_b64=client_public_key,
            sender_private_key_b64=get_server_private_key(),
        )
        return super().render(sealed.to_dict(), accepted_media_type, renderer_context)


def encrypted_endpoint(view_func):
    """
    Opts a function-based view into encrypted request/response handling.

    Apply *below* ``@api_view`` -- DRF's ``api_view`` decorator reads
    ``parser_classes``/``renderer_classes`` off the function it wraps, the
    same way its own ``@parser_classes``/``@renderer_classes`` decorators do::

        @api_view(['POST'])
        @encrypted_endpoint
        def my_view(request):
            ...

    Rejects with ``DecryptionError`` (400) before the view body runs at all
    if ``X-Client-Public-Key`` is missing. This runs as the view's handler
    body, after DRF's own ``initial()`` (authentication, permissions,
    throttling) has already completed -- matching auth -> permissions ->
    decrypt -- and covers GET/DELETE-style views that never touch
    ``request.data`` and so would never otherwise reach
    ``EncryptedJSONParser``.
    """

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        require_client_public_key(request)
        return view_func(request, *args, **kwargs)

    wrapped.parser_classes = (EncryptedJSONParser,)
    wrapped.renderer_classes = (EncryptedJSONRenderer,)
    return wrapped


class EncryptedPayloadMixin:
    """Class-based-view equivalent of :func:`encrypted_endpoint`."""

    parser_classes = [EncryptedJSONParser]
    renderer_classes = [EncryptedJSONRenderer]

    def initial(self, request, *args, **kwargs):
        # Authentication, permissions and throttling first -- matches
        # auth -> permissions -> decrypt. Runs for every HTTP method,
        # unlike a per-handler check, so GET/DELETE views are covered too.
        super().initial(request, *args, **kwargs)
        require_client_public_key(request)
