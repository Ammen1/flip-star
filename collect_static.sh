#!/bin/bash
# Script to collect static files in Docker container


echo "Collecting static files..."
docker exec flipstar_backend python manage.py collectstatic --noinput

echo "Static files collected successfully!"
echo "Logos should now be visible at /static/images/ethio-logo.png and /static/images/flipstar-logo.png"
