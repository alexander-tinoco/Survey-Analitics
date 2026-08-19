"""Convert engine dataclasses into JSON-safe dictionaries.

Kept apart from the engine so the statistics never learn about serialization,
and apart from the views so the API and the template share one shape. A chart
and an API client disagreeing about what "percentage" means is the kind of
bug that only shows up in a screenshot.
"""

from apps.analytics.engine.descriptive import (
    DatasetSummary,
    NumericSummary,
    QuestionDistribution,
)


def summary_to_dict(summary: DatasetSummary) -> dict:
    """Render a whole dataset summary."""
    return {
        "respondents": summary.respondents,
        "questions": summary.questions,
        "overall_response_rate": summary.overall_response_rate,
        "distributions": [distribution_to_dict(d) for d in summary.distributions],
    }


def distribution_to_dict(distribution: QuestionDistribution) -> dict:
    """Render one question, including the derived values templates need."""
    return {
        "position": distribution.position,
        "text": distribution.text,
        "type": distribution.type,
        "answered": distribution.answered,
        "missing": distribution.missing,
        "response_rate": distribution.response_rate,
        "modal_answer": distribution.modal_answer,
        "counts": [
            {"value": c.value, "count": c.count, "percentage": c.percentage}
            for c in distribution.counts
        ],
        "numeric": numeric_to_dict(distribution.numeric),
    }


def numeric_to_dict(numeric: NumericSummary | None) -> dict | None:
    """Render a numeric summary, or None when the question has none."""
    if numeric is None:
        return None

    return {
        "mean": numeric.mean,
        "median": numeric.median,
        "std_dev": numeric.std_dev,
        "minimum": numeric.minimum,
        "maximum": numeric.maximum,
        "q1": numeric.q1,
        "q3": numeric.q3,
        "is_skewed": numeric.is_skewed,
    }
