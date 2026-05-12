#!/usr/bin/env python3
"""
Automatic Migration Runner for Render Deployment
This script will run Django migrations on startup
"""

import os
import sys
import django
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

def run_migrations():
    """Run Django migrations"""
    try:
        print("🔄 Running Django migrations...")
        django.setup()
        
        from django.core.management import execute_from_command_line
        execute_from_command_line(['manage.py', 'migrate', '--verbosity=2'])
        
        print("✅ Migrations completed successfully!")
        
        # Create superuser if none exists
        from django.contrib.auth.models import User
        if not User.objects.filter(is_superuser=True).exists():
            print("📝 Creating default admin user...")
            User.objects.create_superuser(
                username='admin',
                email='admin@selfistar.com',
                password='admin123'
            )
            print("✅ Admin user created (username: admin, password: admin123)")
        else:
            print("ℹ️ Admin user already exists")
            
        return True
        
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False

if __name__ == "__main__":
    success = run_migrations()
    if not success:
        sys.exit(1)
