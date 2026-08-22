#!/bin/bash

# Flipstar Deployment Script for Ethio Telecom Server (Ubuntu 22.04+)
# Uses Docker Compose v2 (docker compose, with a space).

set -euo pipefail


echo "=== Flipstar Deployment Script ==="
echo "Deploying to Ethio Telecom Server..."

# Require .env
if [ ! -f .env ]; then
    echo "Error: .env file not found. Please create it from env.production.example"
    exit 1
fi

# Load environment variables safely (ignore comments and blank lines)
set -a
# shellcheck disable=SC1091
source .env
set +a

# Stop existing containers
echo "Stopping existing containers..."
docker compose down

# Pull latest code (uncomment if you want the script to pull for you)
# git pull origin master

# Build and start containers
echo "Building and starting containers..."
docker compose up -d --build

# Wait for Postgres to actually accept connections (robust replacement for 'sleep 10')
echo "Waiting for Postgres to be ready..."
for i in {1..30}; do
    if docker compose exec -T postgres pg_isready -U "${DB_USER:-flipstar_user}" -d "${DB_NAME:-flipstar_db}" > /dev/null 2>&1; then
        echo "Postgres is ready."
        break
    fi
    echo "  ...still waiting ($i/30)"
    sleep 2
    if [ "$i" -eq 30 ]; then
        echo "Error: Postgres did not become ready in time."
        exit 1
    fi
done

# Run database migrations
echo "Running database migrations..."
docker compose exec -T backend python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
docker compose exec -T backend python manage.py collectstatic --noinput

# Create / promote super admin (idempotent; uses the create_superadmin management command)
echo "Ensuring super admin exists..."
docker compose exec -T backend python manage.py create_superadmin \
    --username "${ADMIN_USERNAME:-admin}" \
    --email "${ADMIN_EMAIL:-admin@flipstar.com}" \
    --password "${ADMIN_PASSWORD:-admin123}"

echo ""
echo "=== Deployment Complete ==="
echo "Services running:"
docker compose ps
echo ""
echo "Application is available at:"
echo "  - Frontend:  http://<server-ip>/"
echo "  - Backend:   http://<server-ip>:8000/"
echo "  - WebSocket: ws://<server-ip>:8000/ws/"
echo ""
echo "Admin login:"
echo "  Username: ${ADMIN_USERNAME:-admin}"
echo "  Password: (value of ADMIN_PASSWORD in .env)"
