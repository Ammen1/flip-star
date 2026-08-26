from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from api.admin import admin_site

urlpatterns = [
    path('admin/', admin_site.urls),
    path('api/v1/', include('api.urls')),
    path('api/', include('api.urls')),
]

# Always serve media files (Render has no separate web server for media)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Always serve static files (nginx proxies /static/ to backend)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
