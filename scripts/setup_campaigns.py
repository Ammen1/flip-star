#!/usr/bin/env python3
"""
Create migrations for campaign models and run them
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
django.setup()

from django.core.management import execute_from_command_line

def create_campaign_migrations():
    print("Creating campaign migrations...")
    try:
        execute_from_command_line(['manage.py', 'makemigrations', 'api'])
        print("✓ Campaign migrations created")
        return True
    except Exception as e:
        print(f"✗ Failed to create migrations: {e}")
        return False

def run_migrations():
    print("Running migrations...")
    try:
        execute_from_command_line(['manage.py', 'migrate'])
        print("✓ Migrations completed")
        return True
    except Exception as e:
        print(f"✗ Failed to run migrations: {e}")
        return False

if __name__ == '__main__':
    print("=== Campaign Setup ===")
    
    if create_campaign_migrations() and run_migrations():
        print("✓ Campaign system setup complete")
    else:
        print("✗ Campaign setup failed")
