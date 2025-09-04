from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

def favicon_view(request):
    return HttpResponse("", content_type="image/x-icon")

urlpatterns = [
    path("", RedirectView.as_view(url="/medical_access/", permanent=False)),
    path("admin/", admin.site.urls),
    path("medical_access/", include("medical_access.urls")),
    path("favicon.ico", favicon_view),
]

# Serve static files in development and production
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
