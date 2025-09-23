from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from medical_access.admin import medical_admin_site

def favicon_view(request):
    return HttpResponse("", content_type="image/x-icon")

urlpatterns = [
    path("", RedirectView.as_view(url="/medical_access/", permanent=False)),
    # Default Django admin for superusers
    path("admin/", admin.site.urls),
    path("medical_admin/", medical_admin_site.urls),
    path("medical_access/", include("medical_access.urls")),
    # REMOVED: Terminal API endpoints - Redundant with admin actions
    path("accounts/login/", RedirectView.as_view(url="/medical_access/login/", permanent=False)),
    path("favicon.ico", favicon_view),
]

# Serve static files in development and production
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
