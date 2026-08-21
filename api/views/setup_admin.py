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
    
    # Resolved through environment -> Vault -> .env. The password used to
    # default to a well-known literal, so this unauthenticated endpoint would
    # create a superuser with a password published in this repository.
    #
    # NOTE: this endpoint should be deleted. `manage.py create_superadmin` does
    # the same job behind shell access. See docs/security.md.
    from infrastructure.secrets import secret

    username = secret('ADMIN_USERNAME', default='superadmin')
    email = secret('ADMIN_EMAIL', default='admin@example.com')
    password = secret('ADMIN_PASSWORD', default='')

    if not password:
        return JsonResponse(
            {'status': 'error', 'message': 'ADMIN_PASSWORD is not configured.'},
            status=500,
        )
    
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
