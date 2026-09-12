# syntax=docker/dockerfile:1
#
# FlipStar backend image.
#
# Two stages: a builder that compiles wheels, and a runtime that carries only
# the interpreter, the installed packages and the application. The previous
# version reinstalled gcc, libpq-dev and libmagickwand-dev into the runtime
# stage, which defeated the multi-stage split and shipped a compiler in
# production (audit finding H-13).

# ---------------------------------------------------------------------------
# Stage 1 — build wheels
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Build-only toolchain. None of this reaches the runtime image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels --timeout 300 --retries 3 -r requirements.txt


# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

# Debian security fixes first. python:3.11-slim is rebuilt only now and then,
# so it can ship packages Debian has already patched -- perl-base 5.40.1-6
# did, with three CRITICAL CVEs fixed in 5.40.1-6+deb13u1, and the Trivy gate
# rightly refused the image. `apt-get upgrade` takes whatever trixie-security
# has published by build time.
#
# SECURITY_UPDATES is the cache key for this layer: CI passes the date, so a
# cached layer from an earlier day is never reused and fixes arrive within a
# day instead of whenever the base image is next rebuilt.
ARG SECURITY_UPDATES=local
# Runtime-only libraries:
#   ffmpeg     — video transcoding and thumbnail extraction
#   libpq5     — PostgreSQL client library (not the -dev headers)
#   curl       — container health check
RUN echo "security updates as of ${SECURITY_UPDATES}" \
    && apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user. A container escape should not land as root.
RUN groupadd --system --gid 1001 flipstar \
    && useradd --system --uid 1001 --gid flipstar --create-home flipstar

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/* \
    && rm -rf /wheels

COPY --chown=flipstar:flipstar . .

# Writable paths must belong to the runtime user.
RUN mkdir -p /app/media /app/staticfiles \
    && chown -R flipstar:flipstar /app/media /app/staticfiles

# Collect static at build time so the runtime filesystem can stay read-only.
# DJANGO_ENV forces the development settings module for this one command:
# production settings deliberately refuse to load without real credentials, and
# no credentials should ever be present during a build.
RUN DJANGO_ENV=development DJANGO_SETTINGS_MODULE=config.settings.development \
    SECRET_KEY=build-time-only \
    python manage.py collectstatic --noinput --clear

USER flipstar

EXPOSE 8000

# Liveness probe. /api/v1/health/ deliberately does not touch the database,
# so a database blip does not cause a restart loop (see api/urls.py::health_check).
#
# Two details that look optional and are not, both measured against this image
# running under config.settings.production:
#
#   * -H "X-Forwarded-Proto: https" -- production sets SECURE_SSL_REDIRECT, so
#     without it SecurityMiddleware answers 301 before routing ever happens,
#     and `curl --fail` does NOT fail on a 3xx. The previous form therefore
#     exited 0 on every single request and reported the container healthy even
#     when the application behind it was broken -- measured: 301, exit 0. This
#     header satisfies SECURE_PROXY_SSL_HEADER (config/settings/base.py) so
#     is_secure() is true and the request reaches the real view.
#   * an explicit "= 200" comparison rather than trusting --fail's exit status,
#     which treats any 2xx and 3xx alike. Only a genuine 200 now counts as
#     healthy. Measured after this change: 200 {"status":"ok"}.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD test "$(curl --silent --output /dev/null --write-out '%{http_code}' \
        -H 'X-Forwarded-Proto: https' \
        http://localhost:8000/api/v1/health/)" = "200" || exit 1

# Daphne (ASGI) is required — the app serves WebSockets via Django Channels.
# A WSGI server such as gunicorn would silently disable them.
# Exec form so SIGTERM reaches the process directly for a graceful shutdown.
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "--proxy-headers", "config.asgi:application"]
