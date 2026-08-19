"""API routes for the analytics layers, mounted at /api/v1/analytics/."""

from django.urls import path

from .api_views import DescriptiveSummaryView

app_name = "analytics_api"

urlpatterns = [
    path("datasets/<int:pk>/descriptive/", DescriptiveSummaryView.as_view(), name="descriptive"),
]
