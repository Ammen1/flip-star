# FlipStar Backend

Django REST API for FlipStar — a gamified social platform for the Ethiopian
market, with a dual-currency wallet, campaign contests, an ad/boost
marketplace, real-time messaging, and payment integrations with Telebirr and
Onevas.

> **Scope.** This repository is the backend/API server only — `frontend/`
> and `mobile-app/` have already been extracted into their own repositories.
> See [docs/deployment.md](docs/deployment.md).

---

## Architecture

A modular monolith on Django 4.2 + DRF, served over ASGI by Daphne (required —
the app serves WebSockets via Django Channels), with Celery workers for media
processing and push delivery.

```
Client ──TLS──▶ nginx ──▶ Daphne (Django/DRF + Channels)
                             │
                             ├──▶ PostgreSQL 15    (system of record)
                             ├──▶ Redis 7          (cache · channel layer · Celery broker)
                             ├──▶ MinIO / S3       (media)
                             ├──▶ Telebirr         (checkout REST · direct debit SOAP)
                             └──▶ Onevas           (SMS · airtime charging)

Celery worker ──▶ ffmpeg transcode · blurhash · image optimise · FCM push
Celery beat   ──▶ scheduled maintenance
```

### Layering

The application is a **single Django app** (`api`) organised internally by
responsibility. The app label must stay `api`: 86 migrations, every `api_*`
table name, and all ContentType rows depend on it. Splitting it into separate
Django apps requires a pinned `db_table` on each of ~82 models plus paired
`SeparateDatabaseAndState` migrations — a data-migration project, not a refactor.

| Layer | Location | Responsibility |
|---|---|---|
| HTTP | `api/views/` | Request handling, authn/authz, response shaping |
| Contracts | `api/serializers/` | Field validation and representation |
| Business logic | `api/services/` | Workflows: scoring, OTP, presence |
| Providers | `api/integrations/` | Telebirr, Onevas, Web Push clients |
| Data | `api/models/` | Models, grouped by domain |
| Async | `api/tasks/` | Celery tasks |
| Realtime | `api/websockets/` | Channels consumers |
| Cross-cutting | `common/` | Exceptions, middleware, permissions, pagination |
| Adapters | `infrastructure/` | Database, cache, storage configuration |
| Config | `config/settings/` | Per-environment settings |

**Dependency rule:** `common/` and `infrastructure/` never import from `api/`.

---

## Repository structure

```
.
├── api/                        # the single Django app (label: "api")
│   ├── models/                 # core, wallet, subscription, campaign, boost, gift, ...
│   ├── views/                  # one module per domain
│   ├── serializers/
│   ├── services/               # otp, presence, scoring/
│   ├── integrations/           # telebirr/, onevas/, push/
│   ├── tasks/                  # Celery tasks
│   ├── websockets/             # Channels consumers
│   ├── admin/                  # admin site + registrations
│   ├── management/commands/    # operational commands
│   ├── migrations/             # 86 migrations — do not rewrite
│   └── urls.py                 # 243 routes, mounted at /api/v1/
│
├── common/                     # cross-cutting, no business logic
│   ├── exceptions/             # domain errors + DRF handler
│   ├── middleware/             # CORS, request context, logging, media
│   ├── permissions/
│   ├── pagination/
│   └── constants/
│
├── infrastructure/             # connection + config only
│   ├── database/
│   ├── storage/
│   ├── cache/
│   └── external_services/
│
├── config/
│   ├── settings/               # base · development · production · testing
│   ├── urls.py  asgi.py  wsgi.py  routing.py
│
├── tests/                      # unit · integration · e2e · fixtures
├── docs/
├── manage.py  pyproject.toml  Dockerfile  Dockerfile.celery
└── requirements.txt  requirements-dev.txt  .env.example
```

---

## Requirements

- Python 3.11
- PostgreSQL 15
- Redis 7
- ffmpeg (video transcoding and thumbnails)
- Docker + Docker Compose v2 (for the full stack)

---

## Local development

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash)
# source .venv/bin/activate          # macOS / Linux

pip install -r requirements-dev.txt

cp .env.example .env                 # then fill in values
```

Minimum `.env` for a local run without Docker:

```ini
DJANGO_ENV=development
SECRET_KEY=<any 50-char random string>
DEBUG=True
USE_DOCKER_DB=true
DB_ENGINE=django.db.backends.sqlite3
USE_LOCMEM_CACHE=true                # boots without Redis
```

Then:

```bash
python manage.py migrate
python manage.py create_superadmin --username admin --email admin@example.com --password '<pick one>'
python manage.py runserver
```

`runserver` is fine for HTTP work. To exercise WebSockets locally, run Daphne:

```bash
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

### Settings modules

Select with `DJANGO_SETTINGS_MODULE`, or with `DJANGO_ENV` if something still
imports the legacy `config.settings` path.

| Module | Use |
|---|---|
| `config.settings.development` | Local. `DEBUG=True`, permissive CORS, console email. |
| `config.settings.testing` | Test suite. In-memory DB and cache, eager Celery. |
| `config.settings.production` | Deployment. **Refuses to start** on missing or unsafe config. |

Production validates at import time and raises `ImproperlyConfigured` listing
every problem — missing `SECRET_KEY`, an insecure default, `DEBUG=True`,
`CORS_ALLOW_ALL_ORIGINS=true`, or a non-PostgreSQL database. There is
deliberately no SQLite fallback.

---

## Tests

```bash
pytest                          # everything
pytest -m unit                  # no database
pytest -m integration           # database-backed
pytest --cov=api --cov=common   # with coverage
```

Two suites pin the restructure and should be treated as release blockers:

- `tests/integration/test_url_contract.py` — every route still resolves to the
  same path and view. A failure here breaks the released mobile client.
- `tests/integration/test_model_registry.py` — every model stays under the `api`
  app label with its original table name.

---

## Lint and format

One tool (Ruff) covers linting, import sorting, formatting and basic security
checks.

```bash
ruff check .          # lint
ruff check . --fix    # autofix
ruff format .         # format
```

---

## Docker

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py create_superadmin
```

Datastore ports bind to `127.0.0.1` only. Reach them from the host at
`localhost:5433` (Postgres), `localhost:6379` (Redis), `localhost:9001`
(MinIO console).

---

## Production

See [docs/deployment.md](docs/deployment.md). In short:

1. Populate `.env` from `.env.example`. Every value is required — the container
   will not start otherwise.
2. `docker compose up -d --build`
3. `docker compose exec backend python manage.py migrate`
4. Verify: `curl -f https://<host>/api/v1/health/`

Migrations are **not** generated at startup. Author them in development and
commit them; CI enforces this with `makemigrations --check`.

---

## API

243 routes under `/api/v1/`. There is no OpenAPI schema yet — tracked in
[docs/api.md](docs/api.md), along with the error-shape inconsistencies a
client must currently tolerate.

**Postman collection:** [`docs/postman/`](docs/postman/) — 376 requests across 34
folders, generated from Django's URL resolver. Import the collection and the
bundled `FlipStar — Local` environment, run **Authentication → POST auth login**,
and the token is captured into a collection variable automatically. Regenerate
after route changes with `python scripts/generate_postman.py`.

Authentication is DRF `TokenAuthentication`:

```
Authorization: Token <key>
```

Health checks:

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health/` | Liveness. No database access. Safe for probes. |
| `GET /api/v1/health/deep/` | Diagnostics. Touches the database. |

---

## External integrations

| Provider | Purpose | Code |
|---|---|---|
| Telebirr (REST) | Coin purchase checkout, RSA-signed | `api/integrations/telebirr/checkout.py` |
| Telebirr (SOAP) | Direct debit mandates and debits | `api/integrations/telebirr/direct_debit.py` |
| Onevas | SMS OTP delivery, airtime charging | `api/integrations/onevas/`, `api/services/otp.py` |
| Web Push | Browser notifications (VAPID) | `api/integrations/push/webpush.py` |
| FCM | Mobile push | `api/tasks/media.py` |

Details and known gaps: [docs/integrations.md](docs/integrations.md).

---

## Configuration & secrets

Values resolve through `infrastructure/secrets/`, in this order:

```
OS environment  →  HashiCorp Vault  →  .env file  →  built-in default
```

Vault is **optional**. With `VAULT_ADDR` unset, resolution behaves exactly as it
did before Vault was introduced, so nothing breaks by deploying without a Vault
server.

```bash
# Local: run Vault in dev mode alongside the stack
docker compose --profile vault up -d vault
export VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=flipstar-dev-root

python manage.py vault_push --env-file .env            # dry run
python manage.py vault_push --env-file .env --confirm  # write
python manage.py vault_status --show-sources           # verify each key's origin
```

In production use AppRole (`VAULT_ROLE_ID` + `VAULT_SECRET_ID`) and set
`VAULT_REQUIRED=true` so a Vault outage stops the container rather than letting
it start with partial configuration.

> **Environment shadows Vault.** While a secret is still set as an environment
> variable in `docker-compose.yml`, Vault is never consulted for it. Populating
> Vault is only half the migration — you must also delete the `x-secret-env`
> block from Compose. Full guide: [docs/secrets.md](docs/secrets.md).

See [`.env.example`](.env.example) — every variable is documented there.

> **Security notice.** `.env` files were committed to this repository's history
> and credentials were rotated and re-committed several times. Vault protects
> secrets going forward; it does nothing about what is already exposed. Every
> secret that has ever appeared in this repo must be treated as public and
> rotated. See [docs/security.md](docs/security.md).

---

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Layering, boundaries, known duplication |
| [docs/development.md](docs/development.md) | Workflow, conventions, adding a feature |
| [docs/deployment.md](docs/deployment.md) | Deploying, rollback, backend-only extraction |
| [docs/api.md](docs/api.md) | Conventions, error shapes, versioning plan |
| [docs/secrets.md](docs/secrets.md) | Vault setup, resolution order, rotation, bootstrap problem |
| [docs/integrations.md](docs/integrations.md) | Provider contracts and failure modes |
| [docs/security.md](docs/security.md) | Actual posture — supersedes the root `SECURITY_DOCUMENTATION.md` |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common failures and their causes |
