"""Pattern analysis: respondent groups and question polarization.

Caching, locking and queueing come from :mod:`.jobs`, shared with the
relational layer.
"""

from dataclasses import dataclass
from typing import Any

from apps.analytics.engine.patterns import (
    ClusterResult,
    QuestionOpinion,
    find_groups,
    measure_opinion,
)
from apps.surveys.models import Dataset

from .frames import load
from .jobs import CachedAnalysis, JobStatus

ENGINE_VERSION = 1


@dataclass(frozen=True)
class PatternPayload:
    """What the worker stores: both halves of the pattern layer.

    Computed together because they read the same frame, and loading a
    dataset twice to answer two questions about it would double the cost of
    the expensive part.
    """

    clusters: ClusterResult
    opinions: list[QuestionOpinion]


@dataclass(frozen=True)
class PatternReport:
    """The outcome of a request for pattern analysis."""

    status: JobStatus
    payload: PatternPayload | None

    @property
    def is_ready(self) -> bool:
        return self.status is JobStatus.READY

    @property
    def clusters(self) -> ClusterResult | None:
        return self.payload.clusters if self.payload else None

    @property
    def opinions(self) -> list[QuestionOpinion]:
        return self.payload.opinions if self.payload else []

    @property
    def notable(self) -> list[QuestionOpinion]:
        """Questions worth surfacing: clear consensus, or a real split.

        A dashboard that highlights every question highlights nothing.
        """
        return [opinion for opinion in self.opinions if opinion.is_notable]


def _compute(dataset: Dataset) -> PatternPayload:
    response_frame = load(dataset)

    return PatternPayload(
        clusters=find_groups(
            response_frame.frame, response_frame.question_types, response_frame.scales
        ),
        opinions=measure_opinion(
            response_frame.frame, response_frame.question_types, response_frame.scales
        ),
    )


def _enqueue(dataset_id: int) -> None:
    from apps.analytics.tasks import compute_pattern_analysis

    compute_pattern_analysis.delay(dataset_id)


analysis = CachedAnalysis(
    name="patterns", version=ENGINE_VERSION, compute=_compute, enqueue=_enqueue
)


def result_key(dataset_id: int) -> str:
    return analysis.result_key(dataset_id)


def lock_key(dataset_id: int) -> str:
    return analysis.lock_key(dataset_id)


def clear(dataset_id: int) -> None:
    analysis.clear(dataset_id)


def compute_and_cache(dataset_id: int) -> PatternPayload:
    return analysis.compute_and_cache(dataset_id)


def get_report(dataset: Dataset) -> PatternReport:
    result = analysis.get(dataset)
    return PatternReport(status=result.status, payload=result.payload)


def request_analysis(dataset: Dataset) -> PatternReport:
    result = analysis.request(dataset)
    return PatternReport(status=result.status, payload=result.payload)


def group_to_dict(group: Any) -> dict[str, Any]:
    """Render one respondent group."""
    return {
        "label": group.label,
        "size": group.size,
        "share": group.share,
        "characteristics": [
            {
                "question": c.question,
                "answer": c.answer,
                "group_share": c.group_share,
                "overall_share": c.overall_share,
                "lift": c.lift,
            }
            for c in group.characteristics
        ],
    }


def opinion_to_dict(opinion: QuestionOpinion) -> dict[str, Any]:
    """Render one question's opinion profile."""
    return {
        "question": opinion.question,
        "verdict": str(opinion.verdict),
        "modal_share": opinion.modal_share,
        "extreme_share": opinion.extreme_share,
        "dispersion": opinion.dispersion,
        "counts": opinion.counts,
    }


def report_to_dict(report: PatternReport) -> dict[str, Any]:
    """Render a whole pattern report for the API and templates."""
    clusters = report.clusters

    return {
        "status": str(report.status),
        "clusters": {
            "found_structure": bool(clusters and clusters.found_structure),
            "silhouette": clusters.silhouette if clusters else 0.0,
            "respondents_clustered": clusters.respondents_clustered if clusters else 0,
            "rejection_reason": clusters.rejection_reason if clusters else "",
            "groups": [group_to_dict(g) for g in (clusters.groups if clusters else [])],
        },
        "opinions": [opinion_to_dict(o) for o in report.opinions],
        "notable": [opinion_to_dict(o) for o in report.notable],
    }
