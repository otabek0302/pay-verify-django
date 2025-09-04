from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/medical_access/", permanent=False)),
    path("admin/", admin.site.urls),
    path("medical_access/", include("medical_access.urls")),
]
