"""Admin registration for survey ingestion models."""

from django.contrib import admin

from .models import Dataset, Question, Response, Survey


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["name", "owner__email"]


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ["__str__", "version", "respondent_count", "question_count", "uploaded_at"]
    list_filter = ["uploaded_at"]
    # Datasets are immutable once ingested; the admin should not offer to edit
    # counts that no longer match the stored rows.
    readonly_fields = ["version", "source_filename", "respondent_count", "question_count"]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["text", "dataset", "position", "type", "distinct_values", "missing_count"]
    list_filter = ["type"]
    search_fields = ["text"]


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ["respondent_key", "question", "normalized_value", "is_missing"]
    list_filter = ["is_missing"]
    # A dataset holds tens of thousands of rows; loading them into a select
    # widget would make the change page unusable.
    raw_id_fields = ["dataset", "question"]
