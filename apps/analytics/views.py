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
from .presenters import distribution_to_dict, summary_to_dict
from .services import insights, patterns, relational
from .services import record as record_service


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


class RecordView(LoginRequiredMixin, DetailView):
    """One dataset as a single readable record.

    Replaces four separate analysis pages. They forced the reader to know
    which layer answered which question before they could look anything up,
    and gave no way to tell where in the analysis they were.
    """

    model = Dataset
    template_name = "analytics/record.html"
    context_object_name = "dataset"

    def get_queryset(self) -> QuerySet:
        return Dataset.objects.filter(survey__owner=self.request.user).select_related("survey")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        built = record_service.build(self.object)
        clusters = built.patterns.clusters

        context["record"] = built
        context["findings"] = [insights.insight_to_dict(i) for i in built.insights]
        context["distributions"] = [distribution_to_dict(d) for d in built.summary.distributions]
        context["associations"] = [
            relational.association_to_dict(a) for a in built.relational.associations
        ]
        context["clusters"] = clusters
        context["groups"] = [
            patterns.group_to_dict(g) for g in (clusters.groups if clusters else [])
        ]
        context["opinions"] = [patterns.opinion_to_dict(o) for o in built.patterns.opinions]
        # Charts read the same serialized summary the tables render from, so a
        # bar can never disagree with the row beside it.
        context["chart_data"] = summary_to_dict(built.summary)
        return context
