#!/usr/bin/env bash
#
# Run the backend on its own — no Docker, no Postgres, no Redis, no frontend.
#
#   ./scripts/run_local.sh              # start the API on :8000
#   ./scripts/run_local.sh migrate      # any manage.py command
#   ./scripts/run_local.sh shell
#
# Uses a local SQLite database and an in-process cache, so the only requirement
# is the virtualenv. The committed .env points DB_HOST at the `flipstar_postgres`
# container, which is unreachable without Docker — the overrides below take
# precedence because the environment outranks .env in the resolution chain.

set -euo pipefail

cd "$(dirname "$0")/.."

VENV_PY=".venv/Scripts/python.exe"          # Windows / Git Bash
[ -x "$VENV_PY" ] || VENV_PY=".venv/bin/python"   # macOS / Linux

if [ ! -x "$VENV_PY" ]; then
    echo "No virtualenv found. Create one first:" >&2
    echo "    python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt" >&2
    exit 1
fi

# --- Local overrides ---------------------------------------------------------
export DJANGO_SETTINGS_MODULE=config.settings.development
export DEBUG=True

# SQLite instead of the Docker Postgres.
export DB_ENGINE=django.db.backends.sqlite3
export DB_NAME=db.sqlite3
export USE_DOCKER_DB=true          # ignore any stray RENDER/DATABASE_URL

# In-process cache and channel layer instead of Redis. Single process only:
# OTP state is not shared, which is fine locally and wrong in production.
export USE_LOCMEM_CACHE=true

# Vault is not involved locally; secrets come from .env and these overrides.
unset VAULT_ADDR VAULT_TOKEN VAULT_ROLE_ID VAULT_SECRET_ID || true
export VAULT_REQUIRED=false

export LOG_LEVEL="${LOG_LEVEL:-INFO}"

# --- Ensure the database exists ----------------------------------------------
if [ ! -f db.sqlite3 ]; then
    echo "No db.sqlite3 — creating and migrating..."
    "$VENV_PY" manage.py migrate --noinput
    "$VENV_PY" manage.py seed_default_gifts      || true
    "$VENV_PY" manage.py seed_subscription_tiers || true
    echo "Create an admin user with:"
    echo "    ./scripts/run_local.sh create_superadmin --username admin --password '<pick one>'"
fi

# --- Run ---------------------------------------------------------------------
if [ "$#" -gt 0 ]; then
    exec "$VENV_PY" manage.py "$@"
fi

echo "API      http://127.0.0.1:8000/api/health/"
echo "Admin    http://127.0.0.1:8000/admin/"
echo
exec "$VENV_PY" manage.py runserver 127.0.0.1:8000  #jne:8000


