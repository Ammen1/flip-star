"""
The frontend's encrypted-route list must agree with the backend's decorators.

Flipstar-web/api.js keeps ENCRYPTED_ENDPOINT_PREFIXES -- a hand-maintained
mirror of which Django views carry @encrypted_endpoint. The two live in
separate repositories, so nothing forces them to agree, and every disagreement
is silent in both directions:

  frontend encrypts, backend does not decrypt
      request.data is {encrypted, nonce, checksum}, so every field reads as
      missing and the view answers "<field> is required" for something the
      client definitely sent.

  backend decrypts, frontend sends plain JSON
      400 decryption_failed.

Three separate production incidents came from this before the test existed:
ussd-initiate (400 "tier_id is required"), get_coin_balance (500), and
telebirr/auth (400 "access_token is required", which broke SuperApp
auto-login). An audit at the time found 17 mismatched routes.

This parses the real api.js rather than a copy. If it drifts out of the
repository the test skips loudly rather than passing on stale data.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.urls import get_resolver

API_JS = Path(__file__).resolve().parents[2] / 'Flipstar-web' / 'api.js'

# Mismatches that exist today and are not fixed by this change. Each one is a
# live bug -- the client encrypts, the view does not decrypt -- kept here so
# the guard passes on the current tree while still failing the moment a NEW
# mismatch appears. Deleting an entry as it is fixed is the point; the set
# should only ever shrink.
#
# These sit in api/views/direct_debit.py (45 pre-existing lint errors) and
# api/views/privacy.py (15). CI lints changed files, so touching either forces
# a whole-file reformat -- they get their own format-then-fix commit.
KNOWN_BROKEN = {
    '/direct-debit/check-status/',
    '/direct-debit/one-off-subscription/',
    '/privacy/consents/',
    '/privacy/consents/history/',
    '/privacy/consents/update/',
    '/privacy/eu-rights/',
    '/privacy/policy/summary/',
}

# The mirror direction: views that decrypt, called by a client that sends
# plaintext. Now empty, and it should stay that way.
#
# These were recorded as a baseline on the theory that some might be
# mobile-only routes the web app never calls. That theory was wrong, and
# /explorer/trending/ proved it: api.js gates RESPONSE decryption on the same
# isEncryptedEndpoint() check, so a missing entry left the envelope unwrapped
# and every caller read an empty list off it. The Trending tab returned a full
# feed and rendered "Nothing trending yet" -- no error, nothing in the console,
# for as long as the entry was missing.
#
# So an entry here is not "probably fine, mobile-only". It is a feature that
# silently shows nothing. Fix the mismatch rather than adding to this set.
#
# The /messages/* group that used to sit here is gone: api.js excluded all of
# /messages/ as multipart-incompatible when only the message-send route is,
# so the web app sent plaintext to five views that decrypt and got 400 on
# every one -- including creating a conversation to share a post. The
# exclusion is now scoped to that single route, matching mobile.
KNOWN_SERVER_ONLY_ENCRYPTED = set()

# Endpoints excluded here for reasons the URLconf cannot express.
KNOWN_PLAINTEXT = {
    # Provider callbacks: Telebirr POSTs these directly and cannot produce our
    # envelope. Encrypting them would reject real payment confirmations.
    '/wallet/telebirr-callback/',
    '/subscription/telebirr/one-time/callback/',
    # multipart/form-data -- incompatible with a JSON envelope.
    '/campaigns/posts/create/',
    # Called before login, when the client may hold no key material.
    '/subscription/check-superapp/',
}


def _parse_frontend_rules() -> tuple[list[str], list[str]]:
    """Read ENCRYPTED_ENDPOINT_PREFIXES and the early-return exclusions."""
    src = API_JS.read_text(encoding='utf-8')

    block = re.search(r'const ENCRYPTED_ENDPOINT_PREFIXES\s*=\s*\[(.*?)\];', src, re.S)
    if block is None:
        pytest.skip('ENCRYPTED_ENDPOINT_PREFIXES not found in api.js')
    prefixes = re.findall(r'"([^"]+)"', block.group(1))

    body = re.search(r'function isEncryptedEndpoint\([^)]*\)\s*\{(.*?)\n\}', src, re.S)
    if body is None:
        pytest.skip('isEncryptedEndpoint() not found in api.js')
    # Only the `if (endpoint.startsWith("...")) return false;` guards, not
    # every quoted string that happens to appear in the function body.
    excluded = re.findall(r'startsWith\(\s*"([^"]+)"\s*\)\s*\)\s*return\s+false', body.group(1))
    return prefixes, excluded


def _frontend_encrypts(path: str, prefixes: list[str], excluded: list[str]) -> bool:
    if any(path.startswith(x) for x in excluded):
        return False
    return any(path.startswith(p) for p in prefixes)


def _backend_decrypts(callback) -> bool:
    """True when the view decrypts request bodies, however it is wired."""
    for flag in ('_is_encrypted_endpoint', 'encrypted_endpoint'):
        if getattr(callback, flag, False):
            return True

    cls = getattr(callback, 'cls', None) or getattr(callback, 'view_class', None)
    holders = [callback] + ([cls] if cls is not None else [])
    if cls is not None and any(c.__name__ == 'EncryptedPayloadMixin' for c in cls.__mro__):
        return True

    for holder in holders:
        for attr in ('parser_classes', 'renderer_classes'):
            for entry in getattr(holder, attr, None) or []:
                if 'Encrypted' in getattr(entry, '__name__', ''):
                    return True
    return False


def _api_routes():
    """Every concrete /api/v1/ route, as (path, callback)."""
    for outer in get_resolver().url_patterns:
        for inner in getattr(outer, 'url_patterns', []):
            full = f'/{outer.pattern}{inner.pattern}'
            if not full.startswith('/api/v1/'):
                continue
            path = full[len('/api/v1') :]
            if '<' in path:  # parameterised; prefix rules still apply via its parent
                continue
            yield path, inner.callback


@pytest.fixture(scope='module')
def frontend_rules():
    if not API_JS.exists():
        pytest.skip(f'{API_JS} not present in this checkout')
    return _parse_frontend_rules()


def test_no_endpoint_is_encrypted_by_the_client_but_not_the_server(frontend_rules):
    """
    The failure mode that broke ussd-initiate and telebirr/auth.

    The client wraps the body, the view never unwraps it, and every field looks
    absent -- reported to the user as "<field> is required".
    """
    prefixes, excluded = frontend_rules
    broken = [
        (path, getattr(cb, '__name__', repr(cb)))
        for path, cb in _api_routes()
        if path not in KNOWN_PLAINTEXT
        and path not in KNOWN_BROKEN
        and _frontend_encrypts(path, prefixes, excluded)
        and not _backend_decrypts(cb)
    ]

    assert not broken, (
        'These endpoints are encrypted by Flipstar-web but not decrypted by Django, '
        'so every field will read as missing:\n'
        + '\n'.join(f'  {p}  ({n})' for p, n in sorted(broken))
        + '\n\nAdd @encrypted_endpoint to the view, or exclude the path in '
        "api.js's isEncryptedEndpoint()."
    )


def test_no_endpoint_is_decrypted_by_the_server_but_sent_plain(frontend_rules):
    """The mirror image: the view demands an envelope the client never sends."""
    prefixes, excluded = frontend_rules
    broken = [
        (path, getattr(cb, '__name__', repr(cb)))
        for path, cb in _api_routes()
        if path not in KNOWN_SERVER_ONLY_ENCRYPTED
        and _backend_decrypts(cb)
        and not _frontend_encrypts(path, prefixes, excluded)
    ]

    assert not broken, (
        'These endpoints decrypt request bodies but Flipstar-web sends plain JSON, '
        'so every call fails with decryption_failed:\n'
        + '\n'.join(f'  {p}  ({n})' for p, n in sorted(broken))
        + '\n\nAdd the prefix to ENCRYPTED_ENDPOINT_PREFIXES, or drop '
        '@encrypted_endpoint from the view.'
    )


def test_provider_callbacks_are_never_encrypted(frontend_rules):
    """
    Payment callbacks are the expensive direction to get wrong.

    Telebirr POSTs these itself and cannot build our envelope. If one is ever
    encrypted we reject genuine payment confirmations -- money taken, nothing
    delivered, and no error on the paying side.
    """
    prefixes, excluded = frontend_rules
    callbacks = {
        '/wallet/telebirr-callback/',
        '/subscription/telebirr/one-time/callback/',
    }

    for path, cb in _api_routes():
        if path in callbacks:
            assert not _backend_decrypts(cb), (
                f'{path} decrypts request bodies, but Telebirr posts plain SOAP/JSON '
                'to it. Payment confirmations would be rejected.'
            )
            assert not _frontend_encrypts(path, prefixes, excluded), (
                f'{path} is in the frontend encrypted set. It is a provider callback '
                'and must stay plaintext.'
            )
