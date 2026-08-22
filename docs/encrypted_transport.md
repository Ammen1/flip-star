# Encrypted request/response payloads

Wires `common/security/e2e_encryption.py`'s `encrypt_payload`/`decrypt_payload`
into DRF's actual request/response cycle, for endpoints that opt in:

```
client -> encrypted request -> Django auth -> permissions ->
decrypt -> serializer validation -> view -> encrypt response -> client
```

**No endpoint uses this yet.** The mechanism, in `common/security/encrypted_transport.py`,
is built and tested but not attached to anything real -- wiring it into the
wrong or too many endpoints breaks normal client behavior for anything the
client hasn't been updated to encrypt/decrypt. Attaching it to specific
endpoints is a separate, deliberate step.

## Why a Parser/Renderer pair, not middleware

DRF has no Express-style per-route middleware chain. It doesn't need one
here: a custom `Parser` decrypts `request.data` before a serializer ever
sees it, and a custom `Renderer` encrypts the response body after the view
returns -- exactly the two points the flow above needs. Parsing is lazy (DRF
only parses when something touches `request.data`) and runs inside the same
exception-handled `dispatch()` as everything else, so a `DecryptionError` /
`ReplayDetected` raised during decryption reaches the client as a normal
400/409 through the existing `common.exceptions.handlers.api_exception_handler`
-- no new error handling was added for this.

Rendering is different, and matters for how failures are handled: DRF
renders the response body lazily, *outside* `dispatch()`'s try/except, when
Django actually serializes it. An exception raised there either surfaces as
a raw, unhandled 500, or -- worse -- runs after the view's business logic
already executed a side effect (a wallet debit, a mandate creation) that the
caller then never learns the outcome of. So every entry point into this
module validates the client's public key *before* the view body runs at
all, for every HTTP method, not only ones with a request body.

## Wire format

Request body (POST/PUT/PATCH) -- exactly `EncryptedPayload.to_dict()`:

```json
{ "encrypted": "base64...", "nonce": "base64...", "checksum": "hex..." }
```

Response body: the same shape, produced by encrypting the view's normal JSON
output.

The client's own public key is **not** part of that envelope -- it travels
in the `X-Client-Public-Key` header on every request. That keeps it
available independent of whether the request has a body: a GET request has
nothing to decrypt, but its response is still encrypted back to the caller
using the key from that header. There is no per-user client-key registry;
the client asserts its public key on every request rather than registering
it once.

The server's own public key is served at `GET /api/v1/crypto/public-key/`
(see [key_management.md](key_management.md)) -- the client encrypts to that.

## Opting a view in

Function-based (apply `@encrypted_endpoint` *below* `@api_view`, so DRF
reads the parser/renderer classes it sets, the same way `@parser_classes`/
`@renderer_classes` work):

```python
from rest_framework.decorators import api_view
from common.security import encrypted_endpoint

@api_view(['POST'])
@encrypted_endpoint
def my_view(request):
    ...  # request.data is already decrypted; return a plain Response(...)
```

Class-based / ViewSets:

```python
from rest_framework.views import APIView
from common.security import EncryptedPayloadMixin

class MyView(EncryptedPayloadMixin, APIView):
    ...
```

Both reject the request with `DecryptionError` (400) before any view code
runs if `X-Client-Public-Key` is missing.

## Error responses

If the client hasn't identified itself yet (no `X-Client-Public-Key`), the
error response about that fact is sent as **plain JSON**, not encrypted --
the client has no way to decrypt a response explaining that its key was
missing. Once a request carries a valid client key, everything after that
point -- including validation errors and business-rule failures raised deep
in a view -- is encrypted back to that key, since the encrypted channel is
already established by then.

## Tests

`tests/unit/test_encrypted_transport.py` (fakeredis-backed server keypair,
no live Redis or database required): parser decrypt correctness and every
rejection path (missing header, missing envelope field, malformed JSON,
tampered ciphertext, replay), renderer encryption and its plain-JSON
fallback when no client key is known, the `encrypted_endpoint` decorator
rejecting before the wrapped view function runs, `EncryptedPayloadMixin`'s
`initial()` ordering (auth/permissions via `super()` first, then the key
check), and full dispatch-cycle round trips through both a function-based
and a class-based disposable view -- including a GET-only case proving the
response is encrypted purely from the header, with nothing in the request
to decrypt.
