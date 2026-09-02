from urllib.parse import urlsplit

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path

from api.views.media import serve_media

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

# Media is served by api.views.media.serve_media, which supports HTTP range
# requests -- Django 4.2's FileResponse does not, so a client could not seek
# into a video and paid for the whole file to watch any of it.
#
# This replaces django.conf.urls.static.static(), which returns [] whenever
# DEBUG is False; the comment it carried ("Always serve media files") was
# therefore untrue in production, where /media/ was not served at all.
#
# Skipped when MEDIA_URL is absolute: object storage is configured, the URLs
# in API responses point at the bucket, and nothing should be served from here.
_media_prefix = urlsplit(settings.MEDIA_URL)
if not _media_prefix.netloc:
    urlpatterns += [
        re_path(
            r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'),
            serve_media,
            name='serve-media',
        ),
    ]

# Always serve static files (nginx proxies /static/ to backend)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
