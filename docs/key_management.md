# Application identity keypair

The application manages its own X25519 public/private keypair automatically.
It is generated once, persisted in Redis, and loaded (never regenerated) by
every process after that -- see `infrastructure/keys/`. This is the keypair
`common/security/e2e_encryption.py` uses as the server's identity when
encrypting or decrypting payloads.

## Algorithm

| | |
|---|---|
| Algorithm | X25519 (Curve25519 ECDH) |
| Private key | raw 32-byte scalar |
| Public key | raw 32-byte point (the scalar's basepoint multiple) |
| Encoding | standard base64, ASCII |
| Storage | two plain Redis strings, one per half |

X25519 was kept rather than chosen fresh here: it is the same primitive
`common/security/e2e_encryption.py` already uses for payload encryption, for
compatibility with the Node.js reference implementation that module was
ported from. One property of X25519 specifically matters for the state
machine below: a public key is *always* a deterministic function of the
private key (scalar multiplication with the base point) -- there is no
independent public value the way there would be with, say, RSA's modulus.

## Redis keys

| Key | Contents |
|---|---|
| `flipstar:crypto:public_key` | base64 public key |
| `flipstar:crypto:private_key` | base64 private key |
| `flipstar:crypto:init_lock` | transient -- exists only during startup initialization |

These live on Redis logical DB 2 (`settings.REDIS_CRYPTO_URL`), deliberately
separate from the cache (DB 1) and Celery broker (DB 0), so that an
operational cache flush (`cache.clear()`, `redis-cli -n 1 FLUSHDB`) cannot
take the application's identity down with it.

## Startup flow

`config/asgi.py` and `config/wsgi.py` both call
`infrastructure.keys.key_manager.initialize()` right after the Django app
registry is ready, before the process accepts traffic. Whichever one Daphne
or your WSGI server actually imports runs it; calling it from both is
harmless -- the second call in the same process is a no-op once the keypair
is cached in memory. Plain `manage.py` commands (`migrate`, `test`, `shell`,
...) never import either file, so they never trigger this.

```
Redis holds...              Result
---------------------------  --------------------------------------------
both keys, valid             loaded, cached in memory, nothing written
neither key                  generated, stored atomically, then used
private only                 public key re-derived (safe for X25519),
                              persisted, then used
public only                  startup FAILS -- the public half may already
                              be known to another party; a fresh private
                              key would silently invalidate it
both keys, mismatched        startup FAILS -- Redis is left untouched
Redis unreachable            startup FAILS in production. In local
                              development (DEBUG=True) falls back to a
                              temporary in-memory keypair instead, the same
                              convenience USE_LOCMEM_CACHE already gives
                              the cache -- that key does not survive a
                              restart and is never used when DEBUG=False.
```

A distributed lock (`flipstar:crypto:init_lock`, plain `SET NX PX` /
`WATCH+MULTI+EXEC`, no Lua) guards the whole state machine, so two instances
booting at the same moment cannot each generate a different keypair -- the
second one to reach the lock re-reads Redis and finds the first instance's
result instead.

Generation and validation never overwrite an existing key. The only thing
that overwrites both halves at once is the explicit rotation command below.

## Rotation

```
python manage.py crypto_keypair                    # show the current public key; no changes
python manage.py crypto_keypair --rotate --confirm  # generate a new pair and overwrite Redis
```

Rotation is deliberately not automatic. Overwriting the private key
invalidates the public key for anyone who already has it. After rotating,
restart every application instance -- each one caches the keypair in memory
per process and keeps using the old one until it reloads from Redis.

## API endpoint

```
GET /api/v1/crypto/public-key/
Authentication: none (AllowAny) -- the key is meant to be public
```

Response:

```json
{
  "publicKey": "base64...",
  "algorithm": "X25519"
}
```

`503 Service Unavailable` if the keypair failed to initialize (Redis was
down and this is production, or `initialize()` hasn't run yet). Never
returns a private key, in either response shape.

## Security

- The private key is reachable only through
  `infrastructure.keys.key_manager.get_private_key()`, documented as
  internal-only, and used solely inside `common/security/e2e_encryption.py`.
  No serializer, view, or log call ever touches it.
- Log messages describe *state* ("keypair generated and stored", "keypair
  loaded", "keys do not match"), never key material.
- `infrastructure/keys/redis_store.py` is the only module that talks to
  Redis for this data; `infrastructure/keys/service.py` is the only module
  that validates or generates keys. The API view goes through
  `KeyManagementService`, never Redis directly.

## Tests

`tests/unit/test_key_management.py` (fakeredis, no live Redis required):
generation on empty Redis, loading an existing valid pair without
regenerating it, public-only and mismatched-pair startup failures leaving
Redis untouched, private-only recovery via derivation, Redis-unreachable
behavior in both production and DEBUG modes, two instances initializing
concurrently converging on one keypair, the public-key endpoint (200 with no
private key ever present, 503 when uninitialized), no private key material
in logs (including on a validation failure), and that the public key
survives a simulated process restart -- both at the service level and
through the HTTP endpoint.

`tests/unit/test_e2e_encryption.py` covers only that
`get_server_public_key()`/`get_server_private_key()` correctly delegate to
`key_manager` and that the resulting keypair is actually usable for
encryption -- storage and the state machine are this module's job, not
that one's.

## Remaining risks

- The DEBUG-mode ephemeral fallback means a developer running without Redis
  gets a different public key every restart. Fine for local work against a
  single process; would silently break anything that persists a client's
  encrypted-to-this-key state across dev server restarts.
- No alerting is wired up for the "public key exists, private key doesn't"
  and "mismatched pair" failure modes beyond a process failing to start --
  in a container orchestrator that should surface as a crash-loop, but
  confirm your deployment actually pages on that rather than silently
  restarting forever.
