"""Dashboard views for the descriptive layer."""

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views.generic import DetailView

from apps.surveys.models import Dataset

from . import exports
from .presenters import summary_to_dict
from .services import insights, patterns, relational
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


class RelationalDashboardView(LoginRequiredMixin, DetailView):
    """Show the relational analysis, queueing it if it has not run yet."""

    model = Dataset
    template_name = "analytics/relational.html"
    context_object_name = "dataset"

    def get_queryset(self) -> QuerySet:
        return Dataset.objects.filter(survey__owner=self.request.user).select_related("survey")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        # Requesting rather than reading: a first visit should start the work
        # instead of showing an empty page with no explanation.
        report = relational.request_analysis(self.object)

        context["report"] = report
        context["associations"] = [relational.association_to_dict(a) for a in report.associations]
        context["significant_count"] = len(report.significant)
        return context


class PatternDashboardView(LoginRequiredMixin, DetailView):
    """Show respondent groups and question polarization."""

    model = Dataset
    template_name = "analytics/patterns.html"
    context_object_name = "dataset"

    def get_queryset(self) -> QuerySet:
        return Dataset.objects.filter(survey__owner=self.request.user).select_related("survey")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        report = patterns.request_analysis(self.object)

        context["report"] = report
        context["rendered"] = patterns.report_to_dict(report)
        return context


class InsightsView(LoginRequiredMixin, DetailView):
    """The readable findings for a dataset — what the product is for."""

    model = Dataset
    template_name = "analytics/insights.html"
    context_object_name = "dataset"

    def get_queryset(self) -> QuerySet:
        return Dataset.objects.filter(survey__owner=self.request.user).select_related("survey")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        report = insights.build(self.object)

        context["report"] = report
        context["rendered"] = insights.report_to_dict(report)
        return context


class InsightsExportView(LoginRequiredMixin, DetailView):
    """Download the findings as CSV or JSON.

    Refuses to export while a layer is still computing: a file is taken away
    and read later, with no indication that it was a partial answer at the
    moment it was written.
    """

    model = Dataset

    def get_queryset(self) -> QuerySet:
        return Dataset.objects.filter(survey__owner=self.request.user).select_related("survey")

    def get(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        dataset = self.get_object()
        report = insights.build(dataset)

        if not report.is_complete:
            messages.info(
                request,
                "The analysis is still running. The findings will be exportable "
                "once every layer has finished.",
            )
            return redirect("analytics:insights", pk=dataset.pk)

        rendered = insights.report_to_dict(report)
        wants_json = kwargs.get("fmt") == "json"

        if wants_json:
            response = JsonResponse(rendered, json_dumps_params={"indent": 2})
            filename = exports.findings_filename(dataset, "json")
        else:
            response = HttpResponse(
                exports.findings_to_csv(rendered["insights"]),
                content_type="text/csv; charset=utf-8",
            )
            filename = exports.findings_filename(dataset, "csv")

        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
