"""
ASGI entry point.

Daphne serves this. A WSGI server would silently disable WebSockets, so the
container command must not be switched to gunicorn without also moving the
Channels routes elsewhere.

``DJANGO_SETTINGS_MODULE`` defaults to the ``config.settings`` package, which
dispatches on ``DJANGO_ENV``. Deployments should set it explicitly to
``config.settings.production``.
"""

import os

import django
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Must run before the routing module is imported, because consumers import
# models at module scope.
django.setup()

# Refuses to start if Redis-for-cache OR Vault is configured but
# unreachable -- checked independently, so either one alone failing is
# enough. See infrastructure/health/startup.py for the exact conditions.
from infrastructure.health import verify_redis_and_vault  # noqa: E402

verify_redis_and_vault()

# Establishes (or loads) the application's identity keypair before the
# process accepts any traffic. Raises and aborts startup if Redis holds a
# corrupt or half-missing keypair -- see infrastructure/keys/service.py.
from infrastructure.keys import key_manager  # noqa: E402

key_manager.initialize()

import config.routing  # noqa: E402

application = ProtocolTypeRouter(
    {
        'http': get_asgi_application(),
        # NOTE: AuthMiddlewareStack resolves scope["user"] from a Django *session*
        # cookie. This API authenticates with DRF tokens and issues no session, so
        # scope["user"] is always AnonymousUser and both consumers close on
        # connect. Fixing this needs a token-aware middleware -- see
        # docs/troubleshooting.md#websockets-never-connect.
        'websocket': AuthMiddlewareStack(
            URLRouter(config.routing.websocket_urlpatterns)
        ),
    }
)
