from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from api.admin import admin_site

urlpatterns = [
    path('admin/', admin_site.urls),
    # Both mounts serve the same routes; the frontend calls some endpoints
    # unversioned. ORDER MATTERS and is the opposite of what it looks like:
    # URLResolver._populate() walks urlpatterns in REVERSE, so the mount
    # declared LAST is the one reverse() returns for a duplicated URL name.
    # With 'api/' last, reverse('auth-login') yielded /api/auth/login/ and 45
    # assertions in tests/integration/test_url_contract.py failed -- along
    # with every absolute URL the app builds for callbacks and emails.
    # Keep 'api/v1/' last so reverse() stays versioned.
    path('api/', include('api.urls')),
    path('api/v1/', include('api.urls')),
]

# Always serve media files (Render has no separate web server for media)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Always serve static files (nginx proxies /static/ to backend)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
