import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = get_wsgi_application()

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
