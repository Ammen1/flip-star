"""
Tests for common/security/encrypted_transport.py -- the DRF Parser/Renderer
pair and view decorators/mixin that wire encrypt_payload/decrypt_payload
into the actual request/response cycle.

No real endpoint uses these yet (deliberately -- see the module docstring
and the conversation that added this file for why scope is held back
pending which endpoints actually need it). These tests build disposable
views with APIRequestFactory rather than touching a real URL, and need no
database.
"""

from __future__ import annotations

import io
import json

import fakeredis
import pytest
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from common.exceptions import DecryptionError, ReplayDetected
from common.security.e2e_encryption import decrypt_payload, encrypt_payload, generate_keypair
from common.security.encrypted_transport import (
    CLIENT_PUBLIC_KEY_HEADER_NAME,
    EncryptedJSONParser,
    EncryptedJSONRenderer,
    EncryptedPayloadMixin,
    encrypted_endpoint,
)
from infrastructure.keys import redis_store

pytestmark = pytest.mark.unit

factory = APIRequestFactory()


@pytest.fixture
def _server_keys():
    """Initialize the shared key_manager singleton against a fresh fake Redis."""
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def client_keys():
    """A pretend mobile client's own long-term keypair: (public, private)."""
    return generate_keypair()


def _encrypted_envelope(plaintext_dict, *, sender_private_key, receiver_public_key):
    sealed = encrypt_payload(
        plaintext_dict, receiver_public_key_b64=receiver_public_key,
        sender_private_key_b64=sender_private_key,
    )
    return sealed.to_dict()


def _parser_context(request):
    return {'request': request, 'encoding': 'utf-8'}


# ---------------------------------------------------------------------------
# EncryptedJSONParser
# ---------------------------------------------------------------------------

def test_parse_decrypts_a_valid_envelope(_server_keys, client_keys):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys

    envelope = _encrypted_envelope(
        {'amount': 100}, sender_private_key=client_private_key, receiver_public_key=server_public_key,
    )
    request = factory.post('/x/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)
    stream = io.BytesIO(json.dumps(envelope).encode())

    data = EncryptedJSONParser().parse(stream, parser_context=_parser_context(request))

    assert data == {'amount': 100}


def test_parse_empty_body_returns_empty_dict(_server_keys, client_keys):
    client_public_key, _ = client_keys
    request = factory.post('/x/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)

    data = EncryptedJSONParser().parse(io.BytesIO(b''), parser_context=_parser_context(request))

    assert data == {}


def test_parse_missing_header_raises(_server_keys):
    request = factory.post('/x/')
    stream = io.BytesIO(json.dumps({'encrypted': 'x', 'nonce': 'y', 'checksum': 'z'}).encode())

    with pytest.raises(DecryptionError, match=CLIENT_PUBLIC_KEY_HEADER_NAME):
        EncryptedJSONParser().parse(stream, parser_context=_parser_context(request))


@pytest.mark.parametrize('missing_field', ['encrypted', 'nonce', 'checksum'])
def test_parse_missing_envelope_field_raises(_server_keys, client_keys, missing_field):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys
    envelope = _encrypted_envelope(
        {'x': 1}, sender_private_key=client_private_key, receiver_public_key=server_public_key,
    )
    del envelope[missing_field]
    request = factory.post('/x/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)

    with pytest.raises(DecryptionError):
        EncryptedJSONParser().parse(
            io.BytesIO(json.dumps(envelope).encode()), parser_context=_parser_context(request),
        )


def test_parse_malformed_json_raises(_server_keys, client_keys):
    client_public_key, _ = client_keys
    request = factory.post('/x/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)

    with pytest.raises(DecryptionError):
        EncryptedJSONParser().parse(
            io.BytesIO(b'not json'), parser_context=_parser_context(request),
        )


def test_parse_tampered_ciphertext_raises(_server_keys, client_keys):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys
    envelope = _encrypted_envelope(
        {'x': 1}, sender_private_key=client_private_key, receiver_public_key=server_public_key,
    )
    envelope['encrypted'] = envelope['encrypted'][:-4] + ('AAAA' if envelope['encrypted'][-4:] != 'AAAA' else 'BBBB')
    request = factory.post('/x/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)

    with pytest.raises(DecryptionError):
        EncryptedJSONParser().parse(
            io.BytesIO(json.dumps(envelope).encode()), parser_context=_parser_context(request),
        )


def test_parse_replayed_nonce_raises_replay_detected(_server_keys, client_keys):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys
    envelope = _encrypted_envelope(
        {'x': 1}, sender_private_key=client_private_key, receiver_public_key=server_public_key,
    )
    request = factory.post('/x/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)

    # First delivery: fine.
    EncryptedJSONParser().parse(
        io.BytesIO(json.dumps(envelope).encode()), parser_context=_parser_context(request),
    )
    # Same bytes again -- a replay.
    with pytest.raises(ReplayDetected):
        EncryptedJSONParser().parse(
            io.BytesIO(json.dumps(envelope).encode()), parser_context=_parser_context(request),
        )


# ---------------------------------------------------------------------------
# EncryptedJSONRenderer
# ---------------------------------------------------------------------------

def test_render_encrypts_to_the_client_public_key(_server_keys, client_keys):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys
    request = factory.get('/x/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)

    rendered = EncryptedJSONRenderer().render(
        {'balance': 500}, renderer_context={'request': request},
    )
    envelope = json.loads(rendered)

    assert set(envelope) == {'encrypted', 'nonce', 'checksum'}
    plaintext = decrypt_payload(
        envelope['encrypted'], envelope['nonce'], server_public_key,
        envelope['checksum'], client_private_key,
    )
    assert json.loads(plaintext) == {'balance': 500}


def test_render_none_data_returns_empty_bytes(_server_keys, client_keys):
    client_public_key, _ = client_keys
    request = factory.get('/x/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)

    assert EncryptedJSONRenderer().render(None, renderer_context={'request': request}) == b''


def test_render_without_client_key_falls_back_to_plain_json(_server_keys, caplog):
    request = factory.get('/x/')  # no header

    with caplog.at_level('WARNING'):
        rendered = EncryptedJSONRenderer().render(
            {'balance': 500}, renderer_context={'request': request},
        )

    assert json.loads(rendered) == {'balance': 500}
    assert any('client public key' in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# encrypted_endpoint (function-based views)
# ---------------------------------------------------------------------------

def test_encrypted_endpoint_sets_parser_and_renderer_classes():
    def view(request):
        return None

    wrapped = encrypted_endpoint(view)

    assert wrapped.parser_classes == (EncryptedJSONParser,)
    assert wrapped.renderer_classes == (EncryptedJSONRenderer,)


def test_encrypted_endpoint_rejects_before_view_runs_when_header_missing():
    calls = []

    @encrypted_endpoint
    def view(request):
        calls.append(request)
        return 'should not reach here'

    request = factory.post('/x/')

    with pytest.raises(DecryptionError):
        view(request)

    assert calls == []


def test_encrypted_endpoint_calls_view_when_header_present(client_keys):
    client_public_key, _ = client_keys
    calls = []

    @encrypted_endpoint
    def view(request):
        calls.append(request)
        return 'ok'

    request = factory.post('/x/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)

    assert view(request) == 'ok'
    assert calls == [request]


# ---------------------------------------------------------------------------
# EncryptedPayloadMixin (class-based views)
# ---------------------------------------------------------------------------

class _StubBase:
    """Stands in for APIView.initial() to test ordering without a real dispatch."""

    def __init__(self):
        self.super_initial_called = False

    def initial(self, request, *args, **kwargs):
        self.super_initial_called = True


class _MixedView(EncryptedPayloadMixin, _StubBase):
    pass


def test_mixin_class_attributes():
    assert EncryptedPayloadMixin.parser_classes == [EncryptedJSONParser]
    assert EncryptedPayloadMixin.renderer_classes == [EncryptedJSONRenderer]


def test_mixin_initial_calls_super_before_checking_header(client_keys):
    client_public_key, _ = client_keys
    view = _MixedView()
    request = factory.get('/x/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)

    view.initial(request)

    assert view.super_initial_called is True


def test_mixin_initial_raises_when_header_missing():
    view = _MixedView()
    request = factory.get('/x/')

    with pytest.raises(DecryptionError):
        view.initial(request)

    # super().initial() still ran (auth/permissions/throttling happen even
    # though decryption then rejects the request).
    assert view.super_initial_called is True


# ---------------------------------------------------------------------------
# End to end: a real DRF dispatch cycle, function-based and class-based
# ---------------------------------------------------------------------------

@api_view(['POST'])
@encrypted_endpoint
def _echo_view(request):
    return Response({'received': request.data})


class _EchoView(EncryptedPayloadMixin, APIView):
    def post(self, request):
        return Response({'received': request.data})

    def get(self, request):
        return Response({'status': 'ok'})


def test_full_round_trip_function_based_view(_server_keys, client_keys):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys

    envelope = _encrypted_envelope(
        {'amount': 100}, sender_private_key=client_private_key, receiver_public_key=server_public_key,
    )
    request = factory.post(
        '/echo/', data=json.dumps(envelope), content_type='application/json',
        HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
    )

    response = _echo_view(request)
    response.render()

    assert response.status_code == 200
    envelope_out = json.loads(response.content)
    assert set(envelope_out) == {'encrypted', 'nonce', 'checksum'}

    plaintext = decrypt_payload(
        envelope_out['encrypted'], envelope_out['nonce'], server_public_key,
        envelope_out['checksum'], client_private_key,
    )
    assert json.loads(plaintext) == {'received': {'amount': 100}}


def test_full_round_trip_class_based_view(_server_keys, client_keys):
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys

    envelope = _encrypted_envelope(
        {'note': 'hi'}, sender_private_key=client_private_key, receiver_public_key=server_public_key,
    )
    request = factory.post(
        '/echo/', data=json.dumps(envelope), content_type='application/json',
        HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
    )

    response = _EchoView.as_view()(request)
    response.render()

    assert response.status_code == 200
    envelope_out = json.loads(response.content)
    plaintext = decrypt_payload(
        envelope_out['encrypted'], envelope_out['nonce'], server_public_key,
        envelope_out['checksum'], client_private_key,
    )
    assert json.loads(plaintext) == {'received': {'note': 'hi'}}


def test_get_request_with_no_body_still_gets_an_encrypted_response(_server_keys, client_keys):
    """Proves the response is encrypted purely off the header, with nothing to decrypt on the way in."""
    server_public_key = _server_keys
    client_public_key, client_private_key = client_keys

    request = factory.get('/echo/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)

    response = _EchoView.as_view()(request)
    response.render()

    assert response.status_code == 200
    envelope_out = json.loads(response.content)
    assert set(envelope_out) == {'encrypted', 'nonce', 'checksum'}
    plaintext = decrypt_payload(
        envelope_out['encrypted'], envelope_out['nonce'], server_public_key,
        envelope_out['checksum'], client_private_key,
    )
    assert json.loads(plaintext) == {'status': 'ok'}


def test_full_dispatch_rejects_before_view_runs_when_header_missing(_server_keys):
    request = factory.post('/echo/', data=json.dumps({}), content_type='application/json')

    response = _echo_view(request)
    response.render()

    assert response.status_code == 400
    # Error response with no known client key falls back to plain JSON --
    # the client can't decrypt a response about "you sent no key" anyway.
    body = json.loads(response.content)
    assert CLIENT_PUBLIC_KEY_HEADER_NAME in body.get('error', '')
