"""
Django admin registration.

Split by domain:

* ``site``         -- the custom ``SelfieStarAdminSite`` plus social, campaign,
                      wallet and moderation registrations.
* ``subscription`` -- subscription, tier and billing registrations.

Import order matters: ``site`` defines ``admin_site``, which registrations in
both modules attach to. ``config/urls.py`` imports ``admin_site`` from here.
"""

from api.admin.site import admin_site  # noqa: F401  (defines the AdminSite)
from api.admin import subscription  # noqa: F401  (registration side effects)

__all__ = ['admin_site']
