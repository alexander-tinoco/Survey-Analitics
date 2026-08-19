"""Translate stored responses into the wide frames the engine expects.

This is the boundary described in ADR 0001: the only module that knows both
the ORM and pandas. Responses are stored long (one row per answer) because
that is the right shape for storage; the engine wants them wide (one row per
respondent) because that is the shape pandas, scipy and scikit-learn read.
"""

from dataclasses import dataclass

import pandas as pd

from apps.surveys.models import Dataset, QuestionType


@dataclass(frozen=True)
class ResponseFrame:
    """A dataset in the shape the analytics engine reads."""

    frame: pd.DataFrame
    question_types: dict[str, str]
    scales: dict[str, list[str]]


def load(dataset: Dataset) -> ResponseFrame:
    """Load one dataset as a wide frame.

    Read in a single query and pivoted in memory. The alternative — a query
    per question — turns a 40-question survey into 40 round trips for data
    that was written in one pass.
    """
    rows = list(
        dataset.responses.values_list(
            "respondent_key",
            "question__position",
            "question__text",
            "normalized_value",
            "numeric_value",
            "is_missing",
        )
    )

    questions = list(dataset.questions.values_list("position", "text", "type"))
    columns = [text for _, text, _ in questions]
    question_types = {text: question_type for _, text, question_type in questions}

    if not rows:
        return ResponseFrame(
            frame=pd.DataFrame(columns=columns), question_types=question_types, scales={}
        )

    long_frame = pd.DataFrame(
        rows,
        columns=["respondent", "position", "question", "value", "numeric", "missing"],
    )
    # A missing answer becomes NA rather than an empty string, so the engine
    # counts it as absent instead of as an answer everyone happened to share.
    long_frame.loc[long_frame["missing"], "value"] = None

    wide = long_frame.pivot(index="respondent", columns="question", values="value")

    return ResponseFrame(
        # Reindexed to the stored question order: pivot sorts columns
        # alphabetically, which would scramble a questionnaire.
        frame=wide.reindex(columns=columns),
        question_types=question_types,
        scales=_recover_scales(long_frame, question_types),
    )


def _recover_scales(
    long_frame: pd.DataFrame, question_types: dict[str, str]
) -> dict[str, list[str]]:
    """Rebuild the answer order of each ordinal question.

    The order is not stored as its own field — it is already implied by the
    rank written into ``numeric_value`` at ingestion. Sorting the distinct
    answers by that rank recovers "Disagree, Neutral, Agree" without a second
    source of truth that could disagree with the stored data.
    """
    ordinal = [
        question
        for question, question_type in question_types.items()
        if question_type == QuestionType.ORDINAL
    ]
    if not ordinal:
        return {}

    answered = long_frame[~long_frame["missing"] & long_frame["numeric"].notna()]
    scales: dict[str, list[str]] = {}

    for question in ordinal:
        points = (
            answered[answered["question"] == question]
            .drop_duplicates(subset="value")
            .sort_values("numeric")["value"]
        )
        if len(points):
            scales[question] = [str(point).lower() for point in points]

    return scales
