"""API routes for the analytics layers, mounted at /api/v1/analytics/."""

from django.urls import path

from .api_views import (
    DescriptiveSummaryView,
    InsightsAPIView,
    PatternAnalysisView,
    RelationalAnalysisView,
)

app_name = "analytics_api"

urlpatterns = [
    path("datasets/<int:pk>/descriptive/", DescriptiveSummaryView.as_view(), name="descriptive"),
    path("datasets/<int:pk>/relational/", RelationalAnalysisView.as_view(), name="relational"),
    path("datasets/<int:pk>/patterns/", PatternAnalysisView.as_view(), name="patterns"),
    path("datasets/<int:pk>/insights/", InsightsAPIView.as_view(), name="insights"),
]
