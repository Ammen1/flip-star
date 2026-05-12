"""
Simple API endpoint to create initial admin user.
Call this once after deploy to create the admin.
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
import json
import os

@csrf_exempt
def setup_admin(request):
    """POST to /api/setup-admin/ to create initial admin user"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    # Get credentials from env vars
    username = os.getenv('ADMIN_USERNAME', 'superadmin')
    email = os.getenv('ADMIN_EMAIL', 'superadmin@postworq.com')
    password = os.getenv('ADMIN_PASSWORD', 'Admin123!')
    
    # Check if already exists
    existing = User.objects.filter(username=username).first()
    if existing:
        if existing.is_superuser:
            return JsonResponse({
                'status': 'already_exists',
                'message': f'Admin user "{username}" already exists',
                'email': email,
                'username': username
            })
        else:
            # Promote
            existing.is_staff = True
            existing.is_superuser = True
            existing.save()
            return JsonResponse({
                'status': 'promoted',
                'message': f'User "{username}" promoted to admin',
                'email': email,
                'username': username
            })
    
    # Create new admin
    try:
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            first_name='Super',
            last_name='Admin'
        )
        return JsonResponse({
            'status': 'created',
            'message': 'Admin user created successfully',
            'email': email,
            'username': username,
            'password_length': len(password)
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
