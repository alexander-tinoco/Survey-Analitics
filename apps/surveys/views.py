"""HTML views for surveys and datasets."""

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch, QuerySet
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    DeleteView,
    DetailView,
    FormView,
    ListView,
)

from .forms import DatasetUploadForm, StartRecordForm
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
    # Without a page size, an account with hundreds of surveys builds every
    # one of them into a single response.
    paginate_by = 20

    def get_queryset(self) -> QuerySet:
        # The list shows each survey's newest dataset. Prefetching it turns
        # one query per row back into two queries total.
        return (
            super()
            .get_queryset()
            .prefetch_related(Prefetch("datasets", queryset=Dataset.objects.order_by("-version")))
        )


class StartRecordView(LoginRequiredMixin, FormView):
    """Name a record and ingest its responses in one step.

    Parsing runs before the survey is created, so a rejected file leaves
    nothing behind: the old two-step flow could strand an empty survey the
    user then had to find and delete.
    """

    form_class = StartRecordForm
    template_name = "surveys/start_record.html"

    def form_valid(self, form: StartRecordForm) -> HttpResponse:
        uploaded = form.cleaned_data["file"]

        try:
            parsed = parse_upload(uploaded.read(), uploaded.name)
        except ParseError as exc:
            # The parser writes for the uploader, who can fix a stray
            # delimiter; the message is surfaced as written.
            form.add_error("file", str(exc))
            return self.form_invalid(form)

        survey = form.save(commit=False)
        survey.owner = self.request.user
        survey.save()

        dataset = ingest(survey, parsed)
        messages.success(
            self.request,
            f"Recorded {dataset.respondent_count} respondents across "
            f"{dataset.question_count} questions.",
        )
        return redirect("analytics:record", pk=dataset.pk)


class SurveyDetailView(OwnedByUserMixin, DetailView):
    model = Survey
    template_name = "surveys/survey_detail.html"
    context_object_name = "survey"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["datasets"] = self.object.datasets.all()
        return context


class SurveyDeleteView(OwnedByUserMixin, DeleteView):
    """Delete a survey and everything ingested under it.

    Cascades to its datasets, questions and responses — for a large survey
    that is tens of thousands of rows, which is why the template spells out
    what is about to go.
    """

    model = Survey
    template_name = "surveys/survey_confirm_delete.html"
    success_url = reverse_lazy("surveys:list")

    def form_valid(self, form: object) -> HttpResponse:
        survey = self.get_object()
        messages.success(self.request, f"Deleted “{survey.name}” and all its uploads.")
        # Datasets are deleted one by one rather than by cascade, so each
        # one's stored file is removed with it. A bulk cascade would drop the
        # rows and leave the uploads orphaned on disk.
        for dataset in survey.datasets.all():
            dataset.delete()
        return super().form_valid(form)


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
            f"Recorded version {dataset.version}: {dataset.respondent_count} "
            f"respondents across {dataset.question_count} questions.",
        )
        return redirect("analytics:record", pk=dataset.pk)


class DatasetDeleteView(LoginRequiredMixin, DeleteView):
    """Delete one uploaded version, leaving the rest of the survey intact."""

    model = Dataset
    template_name = "surveys/dataset_confirm_delete.html"

    def get_queryset(self) -> QuerySet:
        return Dataset.objects.filter(survey__owner=self.request.user).select_related("survey")

    def get_success_url(self) -> str:
        return reverse("surveys:detail", args=[self.object.survey_id])

    def form_valid(self, form: object) -> HttpResponse:
        messages.success(self.request, f"Deleted version {self.object.version}.")
        return super().form_valid(form)


class DatasetFileView(LoginRequiredMixin, DetailView):
    """Serve the file a dataset was ingested from.

    Kept so a parsing fix can be applied to the original rather than
    requiring the user to find and upload it again.
    """

    model = Dataset

    def get_queryset(self) -> QuerySet:
        return Dataset.objects.filter(survey__owner=self.request.user)

    def get(self, request: Any, *args: Any, **kwargs: Any) -> FileResponse:
        dataset = self.get_object()

        if not dataset.source_file:
            # Datasets ingested before file retention existed have no upload
            # to serve, and saying so beats a 500 from a missing path.
            raise Http404("This dataset was ingested before uploads were kept.")

        return FileResponse(
            dataset.source_file.open("rb"),
            as_attachment=True,
            filename=dataset.source_filename,
        )
