"""Root URL configuration.

Feature routes are mounted under ``/api/v1/`` by the milestones that add them;
this module only wires the project-level entry points.
"""

from django.contrib import admin
from django.urls import path

from .views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
]
