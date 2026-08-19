"""HTML routes for the analytics dashboards."""

from django.urls import path

from .views import DescriptiveDashboardView

app_name = "analytics"

urlpatterns = [
    path("datasets/<int:pk>/", DescriptiveDashboardView.as_view(), name="dashboard"),
]
