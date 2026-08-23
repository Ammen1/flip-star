#!/usr/bin/env python3
"""
Reference client for FlipStar's encrypted endpoints.

Twenty endpoints (auth, wallet, direct-debit, charging) refuse a plain JSON
body. Posting one to them returns::

    {"error": "Missing required X-Client-Public-Key header.",
     "code": "decryption_failed"}
    {"error": "Encrypted request body must contain \\"encrypted\\", \\"nonce\\"
     and \\"checksum\\".", "code": "decryption_failed"}

Both mean the same thing: the endpoint expects an encrypted envelope, not
JSON. This script shows exactly what that envelope is, end to end, against a
live server. It is the executable version of docs/encrypted_transport.md.

The scheme is NaCl Box (X25519 + XSalsa20-Poly1305), the same primitive
libsodium and tweetnacl expose, so a JavaScript client mirrors this directly
with tweetnacl's `nacl.box`.

Wire format
-----------
Header  X-Client-Public-Key: <base64 of the client's 32-byte X25519 public key>
Body    {"encrypted": <b64 ciphertext>, "nonce": <b64 24-byte nonce>,
         "checksum": <sha256 hex of the plaintext JSON>}

Three details that are easy to get wrong and produce a generic 400:

* The plaintext is ``json.dumps(data, separators=(',', ':'), sort_keys=True)``
  -- compact separators AND sorted keys. The checksum is taken over that exact
  string, so any other serialisation fails verification even though the
  decryption itself succeeded.
* Send only ``box.encrypt(...).ciphertext``. PyNaCl's ``encrypt()`` returns
  the nonce prepended to the ciphertext; the nonce travels in its own field
  here, so including it twice breaks the decrypt.
* Nonces are single-use for 24 hours. Replaying one returns 409, not 400.

Usage
-----
    pip install pynacl requests

    # smoke test: fetch the server key and prove the round trip
    python scripts/encrypted_request_example.py --base-url https://api.uat.flipstar.et

    # a real call
    python scripts/encrypted_request_example.py \\
        --base-url https://api.uat.flipstar.et \\
        --path /api/v1/auth/register/ \\
        --data '{"username":"someone","email":"a@b.c","password":"123456"}'

    # authenticated endpoint
    python scripts/encrypted_request_example.py \\
        --base-url https://api.uat.flipstar.et \\
        --path /api/v1/wallet/withdraw/ \\
        --token <drf-token> --data '{"amount":100}'

``--insecure`` skips TLS verification, which staging currently needs because
it serves a self-signed certificate.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys

try:
    import nacl.public
    import nacl.utils
    import requests
except ImportError:
    sys.exit('pip install pynacl requests')


CLIENT_PUBLIC_KEY_HEADER = 'X-Client-Public-Key'


def b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode('ascii')


def b64d(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def canonical(data: dict) -> str:
    """The exact serialisation the server checksums. Must match byte for byte."""
    return json.dumps(data, separators=(',', ':'), sort_keys=True)


def checksum(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode('utf-8')).hexdigest()


def encrypt(data: dict, server_public_b64: str, client_private: nacl.public.PrivateKey) -> dict:
    """Build the {encrypted, nonce, checksum} envelope the server expects."""
    box = nacl.public.Box(client_private, nacl.public.PublicKey(b64d(server_public_b64)))
    plaintext = canonical(data)
    nonce = nacl.utils.random(nacl.public.Box.NONCE_SIZE)
    # .ciphertext only -- encrypt() prepends the nonce, and it is sent separately.
    ciphertext = box.encrypt(plaintext.encode('utf-8'), nonce).ciphertext
    return {
        'encrypted': b64e(ciphertext),
        'nonce': b64e(nonce),
        'checksum': checksum(plaintext),
    }


def decrypt(envelope: dict, server_public_b64: str, client_private: nacl.public.PrivateKey) -> str:
    """Decrypt a response envelope and verify its checksum."""
    box = nacl.public.Box(client_private, nacl.public.PublicKey(b64d(server_public_b64)))
    plaintext = box.decrypt(b64d(envelope['encrypted']), b64d(envelope['nonce'])).decode('utf-8')
    if checksum(plaintext) != envelope['checksum']:
        raise ValueError('checksum mismatch -- response was altered in transit')
    return plaintext


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('--base-url', required=True)
    ap.add_argument('--path', help='e.g. /api/v1/auth/register/ (omit for a key smoke test)')
    ap.add_argument('--data', default='{}', help='JSON request body')
    ap.add_argument('--token', help='DRF token for authenticated endpoints')
    ap.add_argument('--insecure', action='store_true', help='skip TLS verification')
    args = ap.parse_args()

    verify = not args.insecure
    if args.insecure:
        requests.packages.urllib3.disable_warnings()  # noqa: S4830

    base = args.base_url.rstrip('/')

    # 1. The server's public key. Public, unauthenticated, safe to cache.
    r = requests.get(f'{base}/api/v1/crypto/public-key/', verify=verify, timeout=30)
    r.raise_for_status()
    server_public = r.json()['publicKey']
    print(f'server public key : {server_public}')
    print(f'algorithm         : {r.json()["algorithm"]}')

    # 2. A client keypair. A real client generates this once and keeps it;
    #    there is no registration step, the key is asserted per request.
    client_private = nacl.public.PrivateKey.generate()
    client_public = b64e(bytes(client_private.public_key))
    print(f'client public key : {client_public}')

    if not args.path:
        print('\nno --path given; key exchange verified, nothing sent')
        return 0

    payload = json.loads(args.data)
    envelope = encrypt(payload, server_public, client_private)

    print(f'\nplaintext         : {canonical(payload)}')
    print(f'checksum          : {envelope["checksum"]}')
    print(f'nonce (b64)       : {envelope["nonce"]}')
    print(f'ciphertext bytes  : {len(b64d(envelope["encrypted"]))}')

    headers = {
        'Content-Type': 'application/json',
        CLIENT_PUBLIC_KEY_HEADER: client_public,
    }
    if args.token:
        headers['Authorization'] = f'Token {args.token}'

    url = f'{base}{args.path}'
    print(f'\nPOST {url}')
    resp = requests.post(url, headers=headers, data=json.dumps(envelope), verify=verify, timeout=60)
    print(f'HTTP {resp.status_code}')

    try:
        body = resp.json()
    except ValueError:
        print(resp.text[:2000])
        return 1

    # Responses from encrypted endpoints come back encrypted too.
    if isinstance(body, dict) and {'encrypted', 'nonce', 'checksum'} <= body.keys():
        print('response is encrypted; decrypting...')
        print(json.dumps(json.loads(decrypt(body, server_public, client_private)), indent=2))
    else:
        # Errors raised before the view runs are returned as plain JSON.
        print(json.dumps(body, indent=2))

    return 0 if resp.ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
