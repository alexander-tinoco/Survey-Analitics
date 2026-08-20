"""Assemble everything one dataset's record page shows, in a single pass.

The four analysis pages this replaces each loaded the dataset independently.
Reading them as one record means loading once and asking each layer what it
has, so a page that shows findings, distributions, relationships and groups
costs one traversal rather than four.
"""

from dataclasses import dataclass
from typing import Any

from apps.analytics.engine.descriptive import DatasetSummary
from apps.analytics.engine.insights import Insight, generate
from apps.surveys.models import Dataset

from . import patterns, relational
from .descriptive import describe
from .patterns import PatternReport
from .relational import RelationalReport


@dataclass(frozen=True)
class Record:
    """One dataset, as the reader encounters it.

    Carries each layer's readiness separately: a record with findings but an
    unfinished pattern layer is a real state, and flattening it into one
    "loading" would hide the findings that are already available.
    """

    dataset: Dataset
    summary: DatasetSummary
    insights: list[Insight]
    relational: RelationalReport
    patterns: PatternReport

    @property
    def is_complete(self) -> bool:
        return self.relational.is_ready and self.patterns.is_ready

    @property
    def pending_layers(self) -> list[str]:
        pending = []
        if not self.relational.is_ready:
            pending.append("relationships")
        if not self.patterns.is_ready:
            pending.append("groups")
        return pending

    @property
    def significant_associations(self) -> list[Any]:
        return self.relational.significant

    @property
    def has_anything_to_report(self) -> bool:
        """Whether the analysis produced a finding worth stating.

        False after a complete run is not an error: it is the product's most
        characteristic answer, and the page renders it as a result.
        """
        return bool(self.insights)


def build(dataset: Dataset) -> Record:
    """Load one dataset's whole record, queueing any layer that has not run.

    Requesting rather than reading: a first visit starts the work instead of
    showing an empty page with no explanation of why it is empty.
    """
    summary = describe(dataset)
    relational_report = relational.request_analysis(dataset)
    pattern_report = patterns.request_analysis(dataset)

    return Record(
        dataset=dataset,
        summary=summary,
        insights=generate(
            summary=summary,
            associations=relational_report.associations,
            clusters=pattern_report.clusters,
            opinions=pattern_report.opinions,
        ),
        relational=relational_report,
        patterns=pattern_report,
    )
