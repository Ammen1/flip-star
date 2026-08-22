"""
Backward-compatible settings dispatcher.

Prefer setting ``DJANGO_SETTINGS_MODULE`` explicitly::

    DJANGO_SETTINGS_MODULE=config.settings.production

Anything that still points at ``config.settings`` (the historical module path)
keeps working: this package selects a concrete module from ``DJANGO_ENV`` and
re-exports it. The default is ``development`` -- deliberately the least
privileged choice, so a misconfigured host fails loudly in development mode
rather than silently serving production traffic with development settings.
"""

import os

DJANGO_ENV = os.environ.get('DJANGO_ENV', 'development').strip().lower()

if DJANGO_ENV in ('production', 'prod'):
    from .production import *  # noqa: F401,F403
elif DJANGO_ENV in ('testing', 'test'):
    from .testing import *  # noqa: F401,F403
else:
    from .development import *  # noqa: F401,F403
