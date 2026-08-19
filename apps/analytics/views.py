"""Dashboard views for the descriptive layer."""

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.views.generic import DetailView

from apps.surveys.models import Dataset

from .presenters import summary_to_dict
from .services.descriptive import describe


class DescriptiveDashboardView(LoginRequiredMixin, DetailView):
    """Show the descriptive analysis of one dataset."""

    model = Dataset
    template_name = "analytics/dashboard.html"
    context_object_name = "dataset"

    def get_queryset(self) -> QuerySet:
        # Ownership is enforced in the queryset, so someone else's dataset id
        # is a 404 rather than a readable page.
        return Dataset.objects.filter(survey__owner=self.request.user).select_related("survey")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        summary = describe(self.object)

        context["summary"] = summary
        # Serialized into the page rather than fetched over a second request:
        # the data is already computed, and a fetch would only add a spinner.
        context["chart_data"] = summary_to_dict(summary)
        return context
