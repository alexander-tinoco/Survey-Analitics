"""HTML routes for the analytics dashboards."""

from django.urls import path

from .views import (
    DescriptiveDashboardView,
    PatternDashboardView,
    RelationalDashboardView,
)

app_name = "analytics"

urlpatterns = [
    path("datasets/<int:pk>/", DescriptiveDashboardView.as_view(), name="dashboard"),
    path(
        "datasets/<int:pk>/relationships/",
        RelationalDashboardView.as_view(),
        name="relational",
    ),
    path("datasets/<int:pk>/groups/", PatternDashboardView.as_view(), name="patterns"),
]
