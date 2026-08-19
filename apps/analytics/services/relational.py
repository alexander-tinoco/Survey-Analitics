"""Relational analysis: caching, queueing, and reading results.

Cross-tabulating every pair of questions is quadratic in the number of
questions — a 30-question survey is 435 chi-square tests — so it runs on a
worker and its result is cached rather than recomputed per page load.

The cache key is safe because of a decision made in ADR 0002: datasets are
immutable and versioned. Re-uploading a file produces a *new* dataset with a
new id, so a key containing that id can never serve results computed from
data the user has since replaced. There is no invalidation to get wrong.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from django.core.cache import cache

from apps.analytics.engine.relational import Association, ContingencyTable, analyze
from apps.surveys.models import Dataset

from .frames import load

# Bumped whenever the statistics change. Cached results computed by an older
# version of the engine are wrong for the new one, and a dataset id alone
# cannot express that — the data did not change, the meaning did.
ENGINE_VERSION = 1

# Results are deterministic for an immutable dataset, so this is a memory
# bound rather than a freshness one: an expired entry is recomputed and comes
# back identical.
RESULT_TTL_SECONDS = 7 * 24 * 60 * 60

# Long enough that a slow job is not queued twice, short enough that a worker
# lost mid-job does not leave the dataset stuck for an hour.
LOCK_TTL_SECONDS = 10 * 60


class JobStatus(StrEnum):
    """What the caller should do next."""

    READY = "ready"
    RUNNING = "running"
    NOT_STARTED = "not_started"


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


def result_key(dataset_id: int) -> str:
    return f"analytics:relational:v{ENGINE_VERSION}:dataset:{dataset_id}"


def lock_key(dataset_id: int) -> str:
    return f"analytics:relational:v{ENGINE_VERSION}:lock:{dataset_id}"


def get_report(dataset: Dataset) -> RelationalReport:
    """Return cached results, or report that a job is running.

    Never computes inline: a request that blocks on 435 chi-square tests is
    exactly what the worker exists to prevent.
    """
    cached = cache.get(result_key(dataset.pk))
    if cached is not None:
        return RelationalReport(status=JobStatus.READY, associations=cached)

    running = cache.get(lock_key(dataset.pk)) is not None
    return RelationalReport(
        status=JobStatus.RUNNING if running else JobStatus.NOT_STARTED,
        associations=[],
    )


def request_analysis(dataset: Dataset) -> RelationalReport:
    """Ensure results exist or a job is on its way to producing them."""
    report = get_report(dataset)
    if report.status is not JobStatus.NOT_STARTED:
        return report

    # cache.add is atomic in Redis: it sets the key only if absent, so two
    # simultaneous requests cannot both win and queue the same job twice.
    if cache.add(lock_key(dataset.pk), True, LOCK_TTL_SECONDS):
        from apps.analytics.tasks import compute_relational_analysis

        compute_relational_analysis.delay(dataset.pk)

    return RelationalReport(status=JobStatus.RUNNING, associations=[])


def compute_and_cache(dataset_id: int) -> list[Association]:
    """Run the analysis and store it. Called by the worker, not by a view."""
    dataset = Dataset.objects.get(pk=dataset_id)
    response_frame = load(dataset)

    associations = analyze(response_frame.frame, response_frame.question_types)

    cache.set(result_key(dataset_id), associations, RESULT_TTL_SECONDS)
    # Released only after the result is stored, so a poller never sees a
    # window with neither a lock nor a result and queues a duplicate job.
    cache.delete(lock_key(dataset_id))

    return associations


def clear(dataset_id: int) -> None:
    """Drop any cached result and lock for a dataset."""
    cache.delete_many([result_key(dataset_id), lock_key(dataset_id)])


def association_to_dict(association: Association) -> dict[str, Any]:
    """Render one association for the API and the templates."""
    return {
        "row_question": association.row_question,
        "column_question": association.column_question,
        "chi_square": association.chi_square,
        "p_value": round(association.p_value, 6),
        "adjusted_p_value": association.adjusted_p_value,
        "degrees_of_freedom": association.degrees_of_freedom,
        "cramers_v": association.cramers_v,
        "strength": str(association.strength),
        "respondents": association.respondents,
        "is_reliable": association.is_reliable,
        "is_significant": association.is_significant,
        "table": _table_to_dict(association.table),
    }


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
