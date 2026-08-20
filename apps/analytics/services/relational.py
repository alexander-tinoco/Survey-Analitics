"""Relational analysis: what the relational layer computes and how it reads.

The caching, locking and queueing live in :mod:`.jobs`, shared with the
pattern layer. What is specific to this analysis is only the computation and
how its results are rendered.
"""

from dataclasses import dataclass
from typing import Any

from apps.analytics.engine.relational import Association, ContingencyTable, analyze
from apps.surveys.models import Dataset

from .frames import load
from .jobs import CachedAnalysis, JobStatus

# Bumped whenever the statistics change.
ENGINE_VERSION = 1


@dataclass(frozen=True)
class RelationalReport:
    """The outcome of a request for relational analysis."""

    status: JobStatus
    associations: list[Association]

    @property
    def is_ready(self) -> bool:
        return self.status is JobStatus.READY

    @property
    def significant(self) -> list[Association]:
        """Only the associations that survived correction and their own
        assumptions — what a reader should actually act on.
        """
        return [a for a in self.associations if a.is_significant]


def _compute(dataset: Dataset) -> list[Association]:
    """Cross-tabulate every testable pair of questions."""
    response_frame = load(dataset)
    return analyze(response_frame.frame, response_frame.question_types, response_frame.scales)


def _enqueue(dataset_id: int) -> None:
    # Imported here: the task module imports this one, and at module level
    # the two would form a cycle.
    from apps.analytics.tasks import compute_relational_analysis

    compute_relational_analysis.delay(dataset_id)


analysis = CachedAnalysis(
    name="relational", version=ENGINE_VERSION, compute=_compute, enqueue=_enqueue
)


def result_key(dataset_id: int) -> str:
    return analysis.result_key(dataset_id)


def lock_key(dataset_id: int) -> str:
    return analysis.lock_key(dataset_id)


def clear(dataset_id: int) -> None:
    analysis.clear(dataset_id)


def compute_and_cache(dataset_id: int) -> list[Association]:
    return analysis.compute_and_cache(dataset_id)


def get_report(dataset: Dataset) -> RelationalReport:
    """Return cached results, or report that a job is running."""
    result = analysis.get(dataset)
    return RelationalReport(status=result.status, associations=result.payload or [])


def request_analysis(dataset: Dataset) -> RelationalReport:
    """Ensure results exist or a job is on its way to producing them."""
    result = analysis.request(dataset)
    return RelationalReport(status=result.status, associations=result.payload or [])


def association_to_dict(association: Association) -> dict[str, Any]:
    """Render one association for the API and the templates."""
    return {
        "row_question": association.row_question,
        "column_question": association.column_question,
        "chi_square": association.chi_square,
        "p_value": round(association.p_value, 6),
        "adjusted_p_value": association.adjusted_p_value,
        "adjusted_p_display": _format_p(association.adjusted_p_value),
        "degrees_of_freedom": association.degrees_of_freedom,
        "cramers_v": association.cramers_v,
        "strength": str(association.strength),
        "respondents": association.respondents,
        "is_reliable": association.is_reliable,
        "is_significant": association.is_significant,
        "table": _table_to_dict(association.table),
    }


# Below this the figure is reported as an inequality. A p-value rounded to
# 0.0 reads as exactly zero, and no test returns exactly zero.
SMALLEST_REPORTED_P = 0.000001


def _format_p(value: float | None) -> str:
    """Render a p-value without ever claiming it is zero."""
    if value is None:
        return "—"
    if value < SMALLEST_REPORTED_P:
        return f"< {SMALLEST_REPORTED_P:g}"
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _table_to_dict(table: ContingencyTable) -> dict[str, Any]:
    """Render a contingency table as rows a template can iterate directly.

    Counts and percentages are zipped together here rather than kept as
    parallel lists. A template cannot index into a list, and adding a filter
    to do it would put layout plumbing between the reader and the numbers.
    """
    percentages = table.row_percentages()

    return {
        "column_labels": table.column_labels,
        "column_totals": table.column_totals,
        "total": table.total,
        "rows": [
            {
                "label": label,
                "total": row_total,
                "cells": [
                    {"count": count, "percentage": percentage}
                    for count, percentage in zip(counts, row_percentages, strict=True)
                ],
            }
            for label, counts, row_percentages, row_total in zip(
                table.row_labels,
                table.counts,
                percentages,
                table.row_totals,
                strict=True,
            )
        ],
    }
