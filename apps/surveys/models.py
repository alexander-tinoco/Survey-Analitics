"""Survey ingestion models.

Responses are stored in long format — one row per (respondent, question) —
rather than a column per question. The reasoning, and the two alternatives
that were rejected, are in ADR 0002.

Datasets are immutable once ingested. Re-uploading a file creates a new
version instead of mutating the old one, which is what lets the analytics
cache key on a dataset id and never serve a stale result.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse


def upload_path(instance: "Dataset", filename: str) -> str:
    """Where an uploaded export is stored.

    Grouped by survey so a survey's uploads stay together on disk, and
    prefixed with the version so two files of the same name do not collide.
    """
    return f"datasets/survey_{instance.survey_id}/v{instance.version}_{filename}"


class QuestionType(models.TextChoices):
    """How a question's answers should be treated statistically.

    The distinction is not cosmetic: it decides which tests are valid. A
    chi-square over free text produces a number, and that number is noise.
    """

    CATEGORICAL = "categorical", "Categorical"
    ORDINAL = "ordinal", "Ordinal"
    NUMERIC = "numeric", "Numeric"
    FREE_TEXT = "free_text", "Free text"


class Survey(models.Model):
    """A survey, stable across re-uploads of its responses."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="surveys"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_survey_name_per_owner")
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("surveys:detail", args=[self.pk])

    @property
    def latest_dataset(self) -> "Dataset | None":
        return self.datasets.first()


class Dataset(models.Model):
    """One uploaded file, frozen at the moment of ingestion.

    Versions increment per survey. Nothing edits a dataset after ingestion:
    a correction is a new upload, so any analysis result stays valid for the
    exact data it was computed from.
    """

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="datasets")
    version = models.PositiveIntegerField()
    source_filename = models.CharField(max_length=255)
    # The upload is kept, not just parsed and discarded. raw_value on each
    # Response protects a single cell, but only the original file allows
    # re-deriving everything after a parser fix — without asking the user to
    # find and upload it again.
    source_file = models.FileField(upload_to=upload_path, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    respondent_count = models.PositiveIntegerField(default=0)
    question_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["survey", "version"], name="unique_version_per_survey")
        ]

    def __str__(self) -> str:
        return f"{self.survey.name} v{self.version}"

    def get_absolute_url(self) -> str:
        return reverse("surveys:dataset_detail", args=[self.pk])

    def delete(self, *args: object, **kwargs: object) -> tuple:
        """Delete the dataset and the file it was ingested from.

        Django removes the row but never the file behind a FileField, so
        deleting datasets would otherwise leave orphaned uploads on disk
        forever.
        """
        stored = self.source_file
        result = super().delete(*args, **kwargs)

        if stored:
            stored.delete(save=False)

        return result


class Question(models.Model):
    """One column of the uploaded file.

    Belongs to a dataset, not to the survey: a later wave can add, drop, or
    reword questions without touching earlier data.
    """

    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="questions")
    position = models.PositiveIntegerField(help_text="Column order in the source file.")
    text = models.TextField()
    type = models.CharField(max_length=20, choices=QuestionType.choices)
    # Cached at ingestion so listing questions does not aggregate every answer.
    distinct_values = models.PositiveIntegerField(default=0)
    missing_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "position"], name="unique_question_position_per_dataset"
            )
        ]

    def __str__(self) -> str:
        return self.text[:80]

    @property
    def answered_count(self) -> int:
        return self.dataset.respondent_count - self.missing_count

    @property
    def is_analyzable(self) -> bool:
        """Free text has no distribution to compare, so it sits out the tests."""
        return self.type != QuestionType.FREE_TEXT


class Response(models.Model):
    """One respondent's answer to one question.

    ``raw_value`` keeps exactly what the file contained, so a parsing bug can
    be fixed by re-deriving the normalized fields instead of asking the user
    to upload again.
    """

    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="responses")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="responses")
    # Identifies a respondent within a dataset. Not a User: respondents are
    # survey participants, not accounts on this application.
    respondent_key = models.CharField(max_length=64)
    raw_value = models.TextField(blank=True)
    normalized_value = models.TextField(blank=True)
    numeric_value = models.FloatField(null=True, blank=True)
    is_missing = models.BooleanField(default=False)

    class Meta:
        indexes = [
            # Per-question aggregation: distributions, contingency tables.
            models.Index(fields=["dataset", "question"], name="response_dataset_question"),
            # Per-respondent reconstruction: clustering, profile building.
            models.Index(fields=["dataset", "respondent_key"], name="response_dataset_person"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "respondent_key"],
                name="unique_answer_per_question_and_respondent",
            )
        ]

    def __str__(self) -> str:
        return f"{self.respondent_key}: {self.raw_value[:40]}"
