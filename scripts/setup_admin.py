#!/usr/bin/env python3
"""
Standalone script to create super admin on Render deploy.
Run this before starting gunicorn.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
django.setup()

from django.contrib.auth.models import User

def create_superadmin():
    # Get credentials from environment variables with defaults
    username = os.getenv('ADMIN_USERNAME', 'superadmin')
    email = os.getenv('ADMIN_EMAIL', 'superadmin@yourapp.com')
    password = os.getenv('ADMIN_PASSWORD', 'Admin123!')
    
    print(f"=== Admin Setup Script Starting ===")
    print(f"ENV ADMIN_USERNAME: {os.getenv('ADMIN_USERNAME', '(using default: superadmin)')}")
    print(f"ENV ADMIN_EMAIL: {os.getenv('ADMIN_EMAIL', '(using default: superadmin@yourapp.com)')}")
    print(f"ENV ADMIN_PASSWORD: {'*' * len(password) if password else '(EMPTY!)'}")
    print(f"")
    print(f"Attempting to create super admin: {username} / {email}")
    print(f"Total users in DB: {User.objects.count()}")
    print(f"Existing superusers: {list(User.objects.filter(is_superuser=True).values('username', 'email'))}")
    print(f"")
    
    # Check if user already exists
    existing = User.objects.filter(username=username).first()
    if existing:
        if existing.is_superuser:
            print(f"✓ Super admin '{username}' already exists - skipping")
            return True
        else:
            # Promote to super admin
            existing.is_staff = True
            existing.is_superuser = True
            existing.save()
            print(f"✓ User '{username}' promoted to super admin")
            return True
    
    # Check if email is taken
    email_exists = User.objects.filter(email=email).exclude(username=username).first()
    if email_exists:
        print(f"⚠ Email '{email}' already used by user: {email_exists.username}")
        return False
    
    # Create super admin
    try:
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            first_name='Super',
            last_name='Admin'
        )
        print(f"✓ Super admin created successfully!")
        print(f"  Username: {username}")
        print(f"  Email: {email}")
        print(f"  Password set: {'Yes' if password else 'NO - EMPTY PASSWORD!'}")
        return True
    except Exception as e:
        print(f"✗ Failed to create super admin: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        print(f"=== Admin Setup Complete ===")
        print(f"Final superusers: {list(User.objects.filter(is_superuser=True).values('username', 'email', 'is_active'))}")

if __name__ == '__main__':
    success = create_superadmin()
    sys.exit(0 if success else 1)
