"""Root URL configuration.

Feature routes are mounted under ``/api/v1/`` by the milestones that add them;
this module wires the project-level entry points and the error handlers.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from .views import health

urlpatterns = [
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("accounts/", include("apps.accounts.urls")),
    path("surveys/", include("apps.surveys.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("api/v1/auth/", include("apps.accounts.api_urls")),
    path("api/v1/analytics/", include("apps.analytics.api_urls")),
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
]

if settings.DEBUG:
    # Development only. In production a web server serves MEDIA_ROOT, and
    # uploads are reached through the ownership-checked download view rather
    # than by guessing a path.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler400 = "config.error_views.bad_request"
handler403 = "config.error_views.permission_denied"
handler404 = "config.error_views.page_not_found"
handler500 = "config.error_views.server_error"
