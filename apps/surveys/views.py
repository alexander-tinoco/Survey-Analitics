"""HTML views for surveys and datasets."""

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import CreateView, DetailView, FormView, ListView

from .forms import DatasetUploadForm, SurveyForm
from .models import Dataset, Survey
from .services.ingestion import ingest
from .services.parsing import ParseError, parse_upload


class OwnedByUserMixin(LoginRequiredMixin):
    """Restrict every queryset to the objects the requester owns.

    Filtering in one place beats checking ownership per view: a forgotten
    check here returns nothing, while a forgotten check per view returns
    someone else's data.
    """

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(**self.ownership_filter())

    def ownership_filter(self) -> dict[str, Any]:
        return {"owner": self.request.user}


class SurveyListView(OwnedByUserMixin, ListView):
    model = Survey
    template_name = "surveys/survey_list.html"
    context_object_name = "surveys"


class SurveyCreateView(LoginRequiredMixin, CreateView):
    model = Survey
    form_class = SurveyForm
    template_name = "surveys/survey_form.html"

    def form_valid(self, form: SurveyForm) -> HttpResponse:
        form.instance.owner = self.request.user
        return super().form_valid(form)


class SurveyDetailView(OwnedByUserMixin, DetailView):
    model = Survey
    template_name = "surveys/survey_detail.html"
    context_object_name = "survey"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["datasets"] = self.object.datasets.all()
        return context


class DatasetUploadView(LoginRequiredMixin, FormView):
    """Parse an uploaded file and store it as a new dataset version."""

    form_class = DatasetUploadForm
    template_name = "surveys/dataset_upload.html"

    def dispatch(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        self.survey = get_object_or_404(Survey, pk=kwargs["pk"], owner=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"survey": self.survey}

    def form_valid(self, form: DatasetUploadForm) -> HttpResponse:
        uploaded = form.cleaned_data["file"]

        try:
            parsed = parse_upload(uploaded.read(), uploaded.name)
        except ParseError as exc:
            # The parser's messages are written for the uploader, so they are
            # surfaced as-is rather than replaced with a generic failure.
            form.add_error("file", str(exc))
            return self.form_invalid(form)

        dataset = ingest(self.survey, parsed)
        messages.success(
            self.request,
            f"Ingested {dataset.respondent_count} respondents "
            f"across {dataset.question_count} questions.",
        )
        return redirect(dataset)


class DatasetDetailView(LoginRequiredMixin, DetailView):
    model = Dataset
    template_name = "surveys/dataset_detail.html"
    context_object_name = "dataset"

    def get_queryset(self) -> QuerySet:
        return Dataset.objects.filter(survey__owner=self.request.user).select_related("survey")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        # Questions are already ordered and counted at ingestion, so listing
        # them costs one query rather than one aggregate per row.
        context["questions"] = self.object.questions.all()
        context["analyzable_count"] = sum(1 for q in context["questions"] if q.is_analyzable)
        return context
