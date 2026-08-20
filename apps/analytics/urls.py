"""HTML routes for the analysis record.

One dataset is one record at one URL. The four routes that used to split it
into separate pages redirect into the record's sections, so links already
handed out keep working and land where the reader expected.
"""

from django.urls import path
from django.views.generic import RedirectView

from .views import InsightsExportView, RecordView

app_name = "analytics"


def section(anchor: str) -> RedirectView:
    """Redirect a retired page to its section of the record."""
    return RedirectView.as_view(pattern_name="analytics:record", permanent=False, query_string=True)


urlpatterns = [
    path("datasets/<int:pk>/", RecordView.as_view(), name="record"),
    path(
        "datasets/<int:pk>/findings/export.<str:fmt>",
        InsightsExportView.as_view(),
        name="insights_export",
    ),
    # Retired pages. Kept so existing links resolve rather than 404.
    path("datasets/<int:pk>/findings/", section("findings"), name="insights"),
    path("datasets/<int:pk>/relationships/", section("relationships"), name="relational"),
    path("datasets/<int:pk>/groups/", section("groups"), name="patterns"),
    path("datasets/<int:pk>/distributions/", section("distributions"), name="dashboard"),
]
