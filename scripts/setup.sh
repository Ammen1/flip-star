#!/bin/bash

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Running migrations..."
python manage.py migrate

echo "Creating superuser..."
python manage.py createsuperuser

echo "Starting Django server..."
python manage.py runserver 8000
