"""
AUTO-PARK – root URL configuration.

API endpoints live under /api/v1/ (see django_app/api/).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("django_app.dashboard.urls")),
    path("parking/", include("django_app.parking.urls")),
    path("accounts/", include("django_app.accounts.urls")),
    path("reports/", include("django_app.reports.urls")),
    path("api/v1/", include("django_app.api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
