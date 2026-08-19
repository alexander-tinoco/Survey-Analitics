"""Assemble readable findings from the three analysis layers.

The insight engine takes the output of the other layers rather than
recomputing anything, so a sentence can never disagree with the table beside
it. That makes this service mostly a matter of gathering what is already
cached and reporting honestly about what is not.
"""

from dataclasses import dataclass
from typing import Any

from apps.analytics.engine.insights import Insight, generate
from apps.surveys.models import Dataset

from . import patterns, relational
from .descriptive import describe


@dataclass(frozen=True)
class InsightReport:
    """The findings available for a dataset right now.

    Which layers were ready is part of the report: an insight list built
    while the relational analysis is still running is incomplete, and saying
    so is the difference between "nothing found" and "not finished".
    """

    insights: list[Insight]
    relational_ready: bool
    patterns_ready: bool

    @property
    def is_complete(self) -> bool:
        return self.relational_ready and self.patterns_ready

    @property
    def pending_layers(self) -> list[str]:
        pending = []
        if not self.relational_ready:
            pending.append("relationships")
        if not self.patterns_ready:
            pending.append("groups")
        return pending


def build(dataset: Dataset) -> InsightReport:
    """Gather findings, requesting the layers that have not run yet.

    The descriptive layer is computed inline because it is cheap; the other
    two are read from cache and queued when missing, so a first visit starts
    the work rather than showing an empty page.
    """
    summary = describe(dataset)
    relational_report = relational.request_analysis(dataset)
    pattern_report = patterns.request_analysis(dataset)

    return InsightReport(
        insights=generate(
            summary=summary,
            associations=relational_report.associations,
            clusters=pattern_report.clusters,
            opinions=pattern_report.opinions,
        ),
        relational_ready=relational_report.is_ready,
        patterns_ready=pattern_report.is_ready,
    )


def insight_to_dict(insight: Insight) -> dict[str, Any]:
    """Render one insight for the API and the templates."""
    return {
        "text": insight.text,
        "kind": str(insight.kind),
        "relevance": insight.relevance,
        "questions": insight.questions,
        "evidence": insight.evidence,
    }


def report_to_dict(report: InsightReport) -> dict[str, Any]:
    """Render a whole insight report."""
    return {
        "complete": report.is_complete,
        "pending": report.pending_layers,
        "insights": [insight_to_dict(insight) for insight in report.insights],
    }
