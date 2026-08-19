"""Produce the descriptive summary for a stored dataset."""

from apps.analytics.engine.descriptive import DatasetSummary, summarize
from apps.surveys.models import Dataset

from .frames import load


def describe(dataset: Dataset) -> DatasetSummary:
    """Summarize a dataset.

    Thin on purpose: loading is one concern, statistics are another, and
    keeping them apart is what lets the statistics be tested without a
    database.
    """
    response_frame = load(dataset)

    return summarize(
        response_frame.frame,
        question_types=response_frame.question_types,
        scales=response_frame.scales,
    )
