#!/usr/bin/env python3
"""
Script to create a test user with phone number for Flipstar.
Run: python create_test_user.py
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
django.setup()

from django.contrib.auth.models import User
from api.models import UserProfile

def create_test_user():
    # Test user credentials
    phone_number = '+251911234567'  # Ethiopian phone number
    username = 'testuser'
    email = 'testuser@ethiotelecom.et'
    password = 'Test123456!'
    
    print(f"=== Creating Test User ===")
    print(f"Phone: {phone_number}")
    print(f"Username: {username}")
    print(f"Email: {email}")
    print(f"Password: {password}")
    print()
    
    # Check if user already exists
    existing_user = User.objects.filter(username=username).first()
    if existing_user:
        print(f"✓ User '{username}' already exists")
        print(f"  Phone: {existing_user.profile.phone_number if hasattr(existing_user, 'profile') else 'N/A'}")
        return existing_user
    
    # Check if phone number already exists
    existing_phone = UserProfile.objects.filter(phone_number=phone_number).first()
    if existing_phone:
        print(f"⚠ Phone number '{phone_number}' already used by: {existing_phone.user.username}")
        return None
    
    # Create user
    try:
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name='Test',
            last_name='User'
        )
        
        # Create profile with phone number
        profile = UserProfile.objects.create(
            user=user,
            phone_number=phone_number,
            is_trial_user=True
        )
        
        print(f"✓ Test user created successfully!")
        print(f"  Username: {username}")
        print(f"  Phone: {phone_number}")
        print(f"  Email: {email}")
        print(f"  Password: {password}")
        return user
    except Exception as e:
        print(f"✗ Failed to create test user: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    user = create_test_user()
    sys.exit(0 if user else 1)
