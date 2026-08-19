"""HTML routes for surveys and datasets."""

from django.urls import path

from .views import (
    DatasetDetailView,
    DatasetUploadView,
    SurveyCreateView,
    SurveyDetailView,
    SurveyListView,
)

app_name = "surveys"

urlpatterns = [
    path("", SurveyListView.as_view(), name="list"),
    path("new/", SurveyCreateView.as_view(), name="create"),
    path("<int:pk>/", SurveyDetailView.as_view(), name="detail"),
    path("<int:pk>/upload/", DatasetUploadView.as_view(), name="upload"),
    path("datasets/<int:pk>/", DatasetDetailView.as_view(), name="dataset_detail"),
]
