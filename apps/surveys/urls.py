"""HTML routes for surveys and datasets."""

from django.urls import path

from .views import (
    DatasetDeleteView,
    DatasetDetailView,
    DatasetFileView,
    DatasetUploadView,
    SurveyCreateView,
    SurveyDeleteView,
    SurveyDetailView,
    SurveyListView,
)

app_name = "surveys"

urlpatterns = [
    path("", SurveyListView.as_view(), name="list"),
    path("new/", SurveyCreateView.as_view(), name="create"),
    path("<int:pk>/", SurveyDetailView.as_view(), name="detail"),
    path("<int:pk>/delete/", SurveyDeleteView.as_view(), name="delete"),
    path("<int:pk>/upload/", DatasetUploadView.as_view(), name="upload"),
    path("datasets/<int:pk>/", DatasetDetailView.as_view(), name="dataset_detail"),
    path("datasets/<int:pk>/delete/", DatasetDeleteView.as_view(), name="dataset_delete"),
    path("datasets/<int:pk>/file/", DatasetFileView.as_view(), name="dataset_file"),
]
