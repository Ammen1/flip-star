from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth.models import AnonymousUser
from rest_framework.response import Response
from rest_framework import status

class SubscriptionRequiredMiddleware(MiddlewareMixin):
    """
    Middleware to check if authenticated users have active subscriptions.
    Redirects users without active subscriptions to subscription page.
    """
    
    # Paths that don't require subscription check
    EXEMPT_PATHS = [
        '/api/auth/',
        '/api/subscription/',
        '/api/health/',
        '/api/settings/public/',
        '/api/posts/',  # Allow viewing posts (GET only)
        '/api/reels/',  # Allow viewing reels (GET only)
        '/api/profile/',  # Allow viewing profiles (GET only)
        '/api/campaigns/',  # Allow viewing campaigns (GET only)
        '/api/search/',  # Allow search (GET only)
        '/api/explorer/',  # Allow explorer (GET only)
        '/api/follows/',  # Allow viewing followers/following (GET only)
        '/api/gamification/',  # Allow gamification features (daily bonuses, spins)
        '/api/wallet/',  # Allow wallet access
        '/api/coins/',  # Allow coin operations
        '/api/messages/',  # Allow messaging features
        '/admin/',
        '/media/',
        '/static/',
    ]
    
    # Specific endpoints that are always exempt (even if they fall under exempt paths)
    ALWAYS_EXEMPT_ENDPOINTS = [
        '/api/posts/create',  # This will be checked separately
        '/api/reels/create',
        '/api/comments/',
        '/api/likes/',
        '/api/gifts/',
        '/api/follows/toggle',
        '/api/saved/',
    ]
    
    # HTTP methods that don't require subscription (GET requests for viewing)
    EXEMPT_METHODS = ['GET', 'HEAD', 'OPTIONS']
    
    def process_request(self, request):
        # Skip for unauthenticated users
        if not request.user or isinstance(request.user, AnonymousUser):
            return None
        
        # Check if user has active subscription
        try:
            from .models_subscription import SubscriptionPlan
            from django.utils import timezone
            
            active_subscription = SubscriptionPlan.objects.filter(
                user=request.user,
                status='active',
                end_date__gt=timezone.now()
            ).first()
            
            if not active_subscription:
                # User has no active subscription
                # Block POST/PUT/DELETE requests (write operations)
                if request.method not in self.EXEMPT_METHODS:
                    # For API requests, return 403 with subscription required info
                    if request.path.startswith('/api/'):
                        return Response({
                            'error': 'Subscription required',
                            'message': 'You need an active subscription to perform this action',
                            'code': 'SUBSCRIPTION_REQUIRED'
                        }, status=status.HTTP_403_FORBIDDEN)
        
        except Exception as e:
            # If there's any error checking subscription, allow the request to proceed
            # to avoid breaking the app
            print(f"[Subscription Middleware] Error: {e}")
            pass
        
        return None

class VideoStreamingMiddleware(MiddlewareMixin):
    """
    Middleware to add proper headers for video streaming
    """
    def process_response(self, request, response):
        # Only apply to video files
        if request.path.startswith('/media/') and any(request.path.endswith(ext) for ext in ['.mp4', '.webm', '.ogg', '.mov']):
            response['Accept-Ranges'] = 'bytes'
            response['Cache-Control'] = 'no-cache'
            
            # Ensure proper content type
            if request.path.endswith('.mp4'):
                response['Content-Type'] = 'video/mp4'
            elif request.path.endswith('.webm'):
                response['Content-Type'] = 'video/webm'
            elif request.path.endswith('.ogg'):
                response['Content-Type'] = 'video/ogg'
            elif request.path.endswith('.mov'):
                response['Content-Type'] = 'video/quicktime'
                
        return response


class CustomCorsMiddleware(MiddlewareMixin):
    """
    Enhanced CORS middleware to ensure proper headers are set for Vercel frontend
    Works even if database connection fails
    """
    
    def process_response(self, request, response):
        # Add CORS headers for all responses - allow all origins
        origin = request.META.get('HTTP_ORIGIN', '')
        
        # Always allow all origins to fix CORS issues
        allowed_origins = [
            'https://uat.flipstar.et',
            'https://postworq.onrender.com',
            'http://localhost:3000',
            'http://localhost:5173',
            'http://localhost:5174',
        ]
        
        if origin in allowed_origins:
            response['Access-Control-Allow-Origin'] = origin
        else:
            response['Access-Control-Allow-Origin'] = '*'
            
        response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD'
        response['Access-Control-Allow-Headers'] = 'accept, accept-encoding, authorization, content-type, dnt, origin, user-agent, x-csrftoken, x-requested-with, x-forwarded-for, x-forwarded-host, x-forwarded-proto'
        response['Access-Control-Allow-Credentials'] = 'true'
        response['Access-Control-Expose-Headers'] = 'content-type, x-csrftoken'
        
        # Handle preflight requests - always allow OPTIONS with CORS headers
        if request.method == 'OPTIONS':
            response.status_code = 200
            if origin in allowed_origins:
                response['Access-Control-Allow-Origin'] = origin
            else:
                response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD'
            response['Access-Control-Allow-Headers'] = 'accept, accept-encoding, authorization, content-type, dnt, origin, user-agent, x-csrftoken, x-requested-with, x-forwarded-for, x-forwarded-host, x-forwarded-proto'
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Max-Age'] = '86400'
            return response
        
        return response
    
    def process_request(self, request):
        # Handle OPTIONS requests early to prevent database connection attempts
        if request.method == 'OPTIONS':
            from django.http import HttpResponse
            response = HttpResponse()
            origin = request.META.get('HTTP_ORIGIN', '')
            
            allowed_origins = [
                'https://uat.flipstar.et',
                'https://postworq.onrender.com',
                'http://localhost:3000',
                'http://localhost:5173',
                'http://localhost:5174',
            ]
            
            if origin in allowed_origins:
                response['Access-Control-Allow-Origin'] = origin
            else:
                response['Access-Control-Allow-Origin'] = '*'
                
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD'
            response['Access-Control-Allow-Headers'] = 'accept, accept-encoding, authorization, content-type, dnt, origin, user-agent, x-csrftoken, x-requested-with, x-forwarded-for, x-forwarded-host, x-forwarded-proto'
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Max-Age'] = '86400'
            return response
        
        return None
