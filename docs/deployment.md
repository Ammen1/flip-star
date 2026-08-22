# Deployment

Single host, Docker Compose, nginx terminating TLS with Let's Encrypt.

## Prerequisites

- Docker 20.10+, Compose v2 (`docker compose`, with a space)
- A populated `.env` at the repository root
- TLS certificates at `/etc/letsencrypt` on the host

## Deploy

```bash
cd /path/to/flipstar
cp .env.example .env             # first time only, then fill it in

docker compose up -d --build
docker compose exec backend python manage.py migrate --noinput
docker compose exec backend python manage.py create_superadmin

curl -f https://<host>/api/v1/health/
docker compose ps
```

## What changed in this revision

| Change | Reason |
|---|---|
| `DJANGO_SETTINGS_MODULE=config.settings.production` | The hardened settings existed but were never selected. HSTS, secure cookies and SSL redirect were all inert. |
| Datastore ports bind to `127.0.0.1` | Postgres, Redis and MinIO were published on all interfaces. Redis had no password. |
| `SECRET_KEY`/`DB_PASSWORD` have no defaults | `changeme` would silently become the production key. |
| Non-root container user, memory limits, health checks | A container escape landed as root; a runaway transcode could starve Postgres. |
| `makemigrations` removed from startup | It generated unreviewed schema changes on the production host. |

### Verify before the first production deploy

Loading production settings turns on `SECURE_SSL_REDIRECT`. Django will now
redirect any request that arrives without `X-Forwarded-Proto: https`.

- nginx sets that header — traffic through it is fine.
- Direct plain-HTTP access to the container will redirect-loop. The compose file
  binds port 8000 to loopback only, so this affects on-host debugging only. Set
  `SECURE_SSL_REDIRECT=false` if you need it.

## Rollback

There is no automated rollback. To revert:

```bash
git checkout <previous-tag>
docker compose up -d --build
```

**Migrations do not roll back automatically.** If a release included a migration,
reverting the code does not revert the schema. Check what was applied:

```bash
docker compose exec backend python manage.py showmigrations api | tail -20
```

and reverse deliberately:

```bash
docker compose exec backend python manage.py migrate api <previous_number>
```

Several migrations are not safely reversible — `0028_wipe_all_posts` deletes from
15 tables with a `noop` reverse. Read the migration before reversing it.

## Known gaps

These are **not** fixed by this revision and need separate work.

### nginx does not route WebSockets or the Django admin

The root `nginx.conf` proxies only `/static/`, `/media/` and `/api/v1/` to the
backend. There is no `/ws/` location and no `Upgrade` headers anywhere, and no
`/admin/` location — both fall through to the React frontend.

The fix, inside the `server { listen 443 ssl; }` block:

```nginx
location /ws/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400;
}

location /admin/ {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

`frontend/nginx.conf` already contains a correct `/ws/` block to copy from.
Note that fixing nginx alone is not sufficient — see
[troubleshooting.md](troubleshooting.md#websockets-never-connect).

### Certificate renewal is undefined

nginx mounts `/etc/letsencrypt` read-only from the host. Nothing in this
repository renews the certificate or reloads nginx afterwards. Confirm certbot is
configured on the host, with a deploy hook that runs
`docker compose exec nginx nginx -s reload`.

### Backups

`backup.sh` at the repository root calls `docker-compose` (v1 syntax) while
`deploy.sh` uses `docker compose` (v2), hardcodes the database name and user,
does not encrypt, and uploads using a variable name the application does not
set. It is not scheduled and there is no restore script. Treat the system as
having no verified recovery path until this is addressed.

MinIO media is not backed up at all.

---

## This repository is backend-only

`frontend/` and `mobile-app/` have already been extracted into their own
repositories, and the remaining backend code has since been flattened to the
repository root (there is no `backend/` subdirectory) -- `docker-compose.yml`,
`nginx.conf`, `deploy.sh`, and `backup.sh` all live alongside `api/`,
`config/`, etc. at the top level. `nginx.conf`'s `location /` no longer
proxies to a `frontend` service; repoint it at wherever the web client is
served from once that's decided.

The `main` / `master` branch divergence noted in earlier revisions of this
doc (`origin/master` carrying its own frontend/mobile work, ~1,416 commits
ahead at the time) is still worth checking before assuming `main` is
current -- `git log main..origin/master` -- but is no longer a blocker for
this extraction specifically, since it already happened on `main`.
