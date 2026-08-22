# Secrets

Configuration is resolved by `infrastructure/secrets/`, which reads from
HashiCorp Vault with the environment and `.env` as fallbacks.

## Resolution order

First hit wins:

| # | Source | Purpose |
|---|---|---|
| 1 | **OS environment** | Operator override and break-glass. How Compose and CI inject values. |
| 2 | **Vault** (KV v2) | Source of truth for secrets once populated. |
| 3 | **`.env` file** | Local development. |
| 4 | **default** | As passed by the calling settings line. |

Environment deliberately outranks Vault so a running deployment can be corrected
without a Vault write. Set `VAULT_PRECEDENCE=vault` to invert 1 and 2 where
Vault must be authoritative.

> **Consequence worth internalising.** While a secret is still present as an
> environment variable in `docker-compose.yml`, Vault is never consulted for it.
> Populating Vault is only half the migration — you must also delete the
> `x-secret-env` block from Compose.

**Vault is optional.** With `VAULT_ADDR` unset, the Vault step is skipped and
resolution behaves exactly as it did before Vault existed. Nothing breaks by
deploying this code without a Vault server.

## Configuration

| Variable | Meaning |
|---|---|
| `VAULT_ADDR` | Vault base URL. Empty disables Vault. |
| `VAULT_ROLE_ID` / `VAULT_SECRET_ID` | AppRole credentials. **Use these in production.** |
| `VAULT_TOKEN` | Token auth. Development and the dev server only. |
| `VAULT_KV_MOUNT` | KV v2 mount point. Default `secret`. |
| `VAULT_SECRET_PATH` | Path within the mount. Default `flipstar/backend`. |
| `VAULT_NAMESPACE` | Vault Enterprise namespace. Optional. |
| `VAULT_REQUIRED` | `true` makes a Vault outage a hard startup failure. |
| `VAULT_PRECEDENCE` | `env` (default) or `vault`. |
| `VAULT_CACERT` | Path to a CA bundle for a private TLS cert. |
| `VAULT_SKIP_VERIFY` | `true` disables TLS verification. **Never in production.** |
| `VAULT_TIMEOUT` | Seconds. Default 5 — this runs during settings import. |

These are *bootstrap* keys: they are read from the environment only, never from
Vault, because reading them from Vault would be circular.

## How it works

`infrastructure/secrets/provider.py` exposes `secret()`, a drop-in replacement
for `decouple.config` with the same signature. The settings modules import it as
`config`, so all ~55 call sites were unchanged:

```python
from infrastructure.secrets import secret as config

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
```

The whole KV path is fetched in **one** read at first use and cached for the
process lifetime. Fetching per key would mean ~55 API calls on every start.

Consequence: **rotating a secret in Vault requires a restart.** That is the
right trade-off for startup configuration. Values that must rotate live —
short-lived database credentials from Vault's dynamic secrets engine — need a
different mechanism and are not implemented.

---

## Local development

Run Vault in dev mode alongside the stack:

```bash
docker compose --profile vault up -d vault
```

Dev mode is in-memory, auto-unsealed, and loses everything on restart. Then:

```bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=flipstar-dev-root

cd backend
python manage.py vault_push --env-file .env            # dry run
python manage.py vault_push --env-file .env --confirm  # write
python manage.py vault_status                          # verify
```

`vault_push` excludes bootstrap and non-secret keys automatically, skips blank
values, and never prints a value.

To confirm Vault is genuinely being used, unset the variable locally and check
that resolution still succeeds:

```bash
unset SECRET_KEY
python manage.py vault_status --show-sources     # SECRET_KEY -> vault
```

---

## Production setup

Dev mode is not suitable. You need a real Vault with persistent storage, TLS,
and a documented unseal procedure.

### 1. Enable KV v2 and write the secrets

```bash
vault secrets enable -path=secret kv-v2
vault kv put secret/flipstar/backend \
    SECRET_KEY="..." \
    DB_PASSWORD="..." \
    TELEBIRR_THIRD_PARTY_PASSWORD="..."
```

### 2. Create a read-only policy

```hcl
# flipstar-backend.hcl
path "secret/data/flipstar/backend" {
  capabilities = ["read"]
}
path "secret/metadata/flipstar/backend" {
  capabilities = ["read", "list"]
}
```

```bash
vault policy write flipstar-backend flipstar-backend.hcl
```

The application only ever reads. `vault_push` writes, and is an operator tool —
give it a separate, more privileged credential, not the app's.

### 3. Configure AppRole

```bash
vault auth enable approle

vault write auth/approle/role/flipstar-backend \
    token_policies="flipstar-backend" \
    token_ttl=1h \
    token_max_ttl=4h \
    secret_id_ttl=0 \
    bind_secret_id=true

vault read  auth/approle/role/flipstar-backend/role-id
vault write -f auth/approle/role/flipstar-backend/secret-id
```

### 4. Point the backend at it

```ini
VAULT_ADDR=https://vault.internal:8200
VAULT_ROLE_ID=<role_id>
VAULT_SECRET_ID=<secret_id>
VAULT_SECRET_PATH=flipstar/backend
VAULT_REQUIRED=true
```

### 5. Remove the secrets from Compose

Delete the `x-secret-env` block from `docker-compose.yml` and its entry in the
`x-django-env` merge. Until you do, environment values shadow Vault.

### 6. Verify, then delete `.env`

```bash
docker compose exec backend python manage.py vault_status
```

Every required key should report `vault`. Only then remove the `.env` file.

---

## The bootstrap problem

Vault does not remove the need to protect one credential — it reduces the
problem from ~25 secrets to one AppRole `secret_id`. That credential still has
to reach the container somehow.

Options, best first:

1. **Response-wrapped secret_id.** A short-lived, single-use wrapping token is
   delivered at deploy time and exchanged for the real `secret_id`. The token is
   useless once used, and use is detectable.
2. **Vault Agent sidecar.** The agent handles auth and renewal and writes a token
   to a shared tmpfs. The application never sees the `secret_id`.
3. **Injected at deploy time** by the CD system from its own secret store, never
   written to disk.
4. **A file on the host** with `0400` permissions owned by the container user.
   Weakest, but still better than 25 secrets in git.

This deployment has no CD system, so option 4 with a documented rotation
schedule is the realistic starting point; option 1 once CD exists.

---

## Rotation

| Secret | Procedure |
|---|---|
| Application secrets | `vault kv put` the new value, then restart the backend and Celery services. |
| AppRole `secret_id` | Issue a new one, update the deployment, restart. Revoke the old with `vault write auth/approle/role/flipstar-backend/secret-id-accessor/destroy`. |
| `SECRET_KEY` | Invalidates sessions and password-reset tokens. DRF auth tokens survive — they are random database rows, not signed. |
| Telebirr / Onevas | Must be reissued by Ethio Telecom; coordinate before rotating. |

Because secrets are cached per process, **every rotation needs a restart** of
`backend`, `celery_worker` and `celery_beat`.

---

## What this does not solve

Vault protects secrets going forward. It does nothing about what is already
exposed:

- `.env`, `.env.production` and `render.env` (formerly nested under a
  `backend/` directory that has since been flattened into the repository
  root) are in git history, across `main`, `master` and `uat`.
- History contains multiple commits rotating and re-committing Telebirr, Onevas
  and CRM credentials.

**Every secret that has ever been in this repository is compromised and must be
rotated regardless of Vault.** Adopting Vault is a good moment to do it, since
you are touching every credential anyway. See [security.md](security.md).

---

## Troubleshooting

**`VAULT_REQUIRED=true but VAULT_ADDR is not set`** — `VAULT_REQUIRED` was
enabled without an address. Set `VAULT_ADDR` or turn the flag off.

**`Vault rejected the supplied credentials`** — token expired, or the AppRole
`secret_id` was consumed or revoked. Issue a new one.

**`VAULT_ADDR is set but the hvac package is not installed`** — rebuild the
image; `hvac==2.3.0` is in `requirements.txt`.

**Values are stale after a Vault write** — expected. The payload is cached per
process; restart the service.

**Vault is populated but old values are still used** — the secret is still set as
an environment variable and environment outranks Vault. Run
`manage.py vault_status --show-sources` to see the origin of each key, then
remove it from Compose.

## If Redis or Vault is down

Not configuring a dependency at all is fine: Vault unconfigured (`VAULT_ADDR`
unset) falls back to environment/.env (that's the whole design above); Redis
not being the cache backend has the `USE_LOCMEM_CACHE` dev escape hatch, and
the E2E identity keypair has its own DEBUG-gated ephemeral fallback
(`docs/key_management.md`).

A dependency that **is** configured but doesn't actually answer is
different. `infrastructure/health/startup.py`'s `verify_redis_and_vault()`
runs at process startup (`config/wsgi.py` and `config/asgi.py` for the API
process, right before the E2E keypair check; `api/celery.py`'s
`worker_init`/`beat_init` signal handlers for Celery workers and beat) and
refuses to start the process if the configured cache backend is Redis and
it's unreachable, **or** if `VAULT_ADDR` is set and Vault is unreachable or
not authenticated. Each is checked independently — either one alone failing
is enough to refuse startup, not just both at once.

```
CriticalInfrastructureUnavailable: Refusing to start -- required
infrastructure is unreachable: Redis is unreachable (Error 111 connecting
to redis:6379. Connection refused.)
```

If you see this naming **Redis**: bring Redis back, or (dev only) set
`USE_LOCMEM_CACHE=true` so the app no longer depends on Redis for its cache
at all.

If you see this naming **Vault**: confirm Vault is actually reachable and
authenticated (`manage.py vault_status`), or unset `VAULT_ADDR` if this
environment isn't meant to use Vault at all.
