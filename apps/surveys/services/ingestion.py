"""Turn a parsed export into database rows.

This is the translation layer described in ADR 0001: it is the only module in
the ingestion path that knows about Django. The parsing and inference it calls
are pure, and the models it writes are pure storage.
"""

import pandas as pd
from django.core.files.base import ContentFile
from django.db import transaction

from ..models import Dataset, Question, QuestionType, Response, Survey
from .inference import (
    InferredType,
    QuestionProfile,
    is_missing,
    normalize_answer,
    profile_frame,
)
from .parsing import ParsedFile

# Rows are written in batches: a 500-respondent, 40-question survey is 20,000
# Response rows, and one INSERT each would make ingestion feel broken.
BATCH_SIZE = 2_000

_TYPE_MAP = {
    InferredType.CATEGORICAL: QuestionType.CATEGORICAL,
    InferredType.ORDINAL: QuestionType.ORDINAL,
    InferredType.NUMERIC: QuestionType.NUMERIC,
    InferredType.FREE_TEXT: QuestionType.FREE_TEXT,
}


@transaction.atomic
def ingest(survey: Survey, parsed: ParsedFile) -> Dataset:
    """Store ``parsed`` as a new version of ``survey``.

    Atomic on purpose: a partially ingested dataset would report a respondent
    count that its rows do not support, and every later analysis would quietly
    compute against incomplete data.
    """
    dataset = Dataset.objects.create(
        survey=survey,
        version=_next_version(survey),
        source_filename=parsed.filename,
        respondent_count=parsed.respondent_count,
        question_count=parsed.question_count,
    )

    if parsed.content:
        # Saved after creation so upload_path can read the version, which is
        # only assigned once the row exists.
        dataset.source_file.save(parsed.filename, ContentFile(parsed.content), save=True)

    profiles = profile_frame(parsed.frame)
    questions = _create_questions(dataset, profiles)
    _create_responses(dataset, parsed.frame, profiles, questions)

    return dataset


def _next_version(survey: Survey) -> int:
    """Version numbers increase and are never reused.

    ``select_for_update`` on the survey row serializes concurrent uploads, so
    two files arriving together cannot both claim the same version.
    """
    Survey.objects.select_for_update().filter(pk=survey.pk).first()
    latest = survey.datasets.order_by("-version").values_list("version", flat=True).first()
    return (latest or 0) + 1


def _create_questions(dataset: Dataset, profiles: list[QuestionProfile]) -> dict[int, Question]:
    """Create one Question per column, keyed by position."""
    created = Question.objects.bulk_create(
        [
            Question(
                dataset=dataset,
                position=profile.position,
                text=profile.text,
                type=_TYPE_MAP[profile.type],
                distinct_values=profile.distinct_values,
                missing_count=profile.missing_count,
            )
            for profile in profiles
        ]
    )
    return {question.position: question for question in created}


def _create_responses(
    dataset: Dataset,
    frame: pd.DataFrame,
    profiles: list[QuestionProfile],
    questions: dict[int, Question],
) -> None:
    """Flatten the wide frame into one row per answer."""
    rows: list[Response] = []

    for row_index, (_, record) in enumerate(frame.iterrows()):
        # Positional, not derived from the data: an export may have no id
        # column, and two respondents may legitimately answer identically.
        respondent_key = f"r{row_index + 1}"

        for profile in profiles:
            raw = record.iloc[profile.position]
            rows.append(
                _build_response(dataset, questions[profile.position], respondent_key, raw, profile)
            )

    Response.objects.bulk_create(rows, batch_size=BATCH_SIZE)


def _build_response(
    dataset: Dataset,
    question: Question,
    respondent_key: str,
    raw: object,
    profile: QuestionProfile,
) -> Response:
    """Build one Response, keeping the original value alongside derived ones."""
    missing = is_missing(raw)
    normalized = "" if missing else normalize_answer(raw)

    return Response(
        dataset=dataset,
        question=question,
        respondent_key=respondent_key,
        raw_value="" if raw is None or pd.isna(raw) else str(raw),
        normalized_value=normalized,
        numeric_value=_numeric_value(normalized, profile) if not missing else None,
        is_missing=missing,
    )


def _numeric_value(normalized: str, profile: QuestionProfile) -> float | None:
    """Derive a sortable number so ranks can be computed in SQL.

    Numeric answers convert directly. Ordinal answers become their position on
    the scale, which is what makes "Agree > Neutral" expressible at all — the
    text alone sorts alphabetically and would put "Agree" above "Neutral" for
    the wrong reason.
    """
    if profile.type is InferredType.NUMERIC:
        return _to_float(normalized)

    if profile.type is InferredType.ORDINAL and profile.scale:
        # A scale stored as digits keeps its own values. Using the position
        # would be right only while every rung is used: on a 1-5 scale where
        # nobody picked 2 or 4, position would turn 3 into 2 and 5 into 3,
        # silently compressing the range every later correlation reads.
        if all(point.lstrip("-").isdigit() for point in profile.scale):
            return _to_float(normalized)

        try:
            return float(profile.scale.index(normalized.lower()) + 1)
        except ValueError:
            return None

    return None


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None
