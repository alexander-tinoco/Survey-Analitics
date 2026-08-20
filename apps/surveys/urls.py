"""HTML routes for surveys and datasets."""

from django.urls import path
from django.views.generic import RedirectView

from .views import (
    DatasetDeleteView,
    DatasetFileView,
    DatasetUploadView,
    StartRecordView,
    SurveyDeleteView,
    SurveyDetailView,
    SurveyListView,
)

app_name = "surveys"

urlpatterns = [
    path("", SurveyListView.as_view(), name="list"),
    path("new/", StartRecordView.as_view(), name="create"),
    path("<int:pk>/", SurveyDetailView.as_view(), name="detail"),
    path("<int:pk>/delete/", SurveyDeleteView.as_view(), name="delete"),
    path("<int:pk>/upload/", DatasetUploadView.as_view(), name="upload"),
    # The dataset's own page is the analysis record; this only keeps old links alive.
    path(
        "datasets/<int:pk>/",
        RedirectView.as_view(pattern_name="analytics:record", permanent=False),
        name="dataset_detail",
    ),
    path("datasets/<int:pk>/delete/", DatasetDeleteView.as_view(), name="dataset_delete"),
    path("datasets/<int:pk>/file/", DatasetFileView.as_view(), name="dataset_file"),
]
