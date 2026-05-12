#!/bin/bash
# Migration and startup script for Render

echo "🔄 Running Django migrations..."
cd backend

echo "Creating new migrations if any..."
python manage.py makemigrations

echo "Applying migrations..."
python manage.py migrate --verbosity=2

echo "🎁 Seeding default gifts..."
python manage.py seed_default_gifts

echo "📦 Collecting static files..."
python manage.py collectstatic --noinput

echo "🚀 Starting Gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 120 --keep-alive 5
