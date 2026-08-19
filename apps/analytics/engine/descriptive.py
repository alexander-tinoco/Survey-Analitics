"""Descriptive statistics over survey responses.

Pure module: DataFrames and dataclasses in, dataclasses out. It must not
import Django, touch the database, or read a file (ADR 0001). A test walks
this package and fails the build if that ever stops being true.

The input is a *wide* frame — one row per respondent, one column per question
— because that is what pandas, scipy and scikit-learn all expect. Translating
the long-format rows into that shape is the service layer's job.
"""

from dataclasses import dataclass

import pandas as pd

# Distributions are capped when rendered: a categorical question with 30
# options produces a chart nobody can read. The remainder is folded into a
# single "other" entry rather than dropped, so percentages still total 100.
MAX_PLOTTED_CATEGORIES = 12


@dataclass(frozen=True)
class ValueCount:
    """One bar of a distribution."""

    value: str
    count: int
    percentage: float


@dataclass(frozen=True)
class NumericSummary:
    """Summary of a numeric question.

    Mean and median are both reported on purpose: when they diverge, the
    distribution is skewed, and that gap is itself a finding.
    """

    mean: float
    median: float
    std_dev: float
    minimum: float
    maximum: float
    q1: float
    q3: float

    @property
    def is_skewed(self) -> bool:
        """Whether mean and median differ enough to matter.

        Measured in standard deviations so the test means the same thing for
        an age column and a 0-10 score.
        """
        if self.std_dev == 0:
            return False
        return abs(self.mean - self.median) / self.std_dev > 0.2


@dataclass(frozen=True)
class QuestionDistribution:
    """How one question was answered."""

    position: int
    text: str
    type: str
    counts: list[ValueCount]
    answered: int
    missing: int
    numeric: NumericSummary | None = None

    @property
    def total(self) -> int:
        return self.answered + self.missing

    @property
    def response_rate(self) -> float:
        """Share of respondents who answered, as a percentage."""
        if self.total == 0:
            return 0.0
        return round(self.answered / self.total * 100, 1)

    @property
    def modal_answer(self) -> str | None:
        """The most common answer, or None when nothing was answered."""
        return self.counts[0].value if self.counts else None


@dataclass(frozen=True)
class DatasetSummary:
    """Everything the descriptive layer knows about one dataset."""

    respondents: int
    questions: int
    distributions: list[QuestionDistribution]

    @property
    def overall_response_rate(self) -> float:
        """Share of all possible answers that were actually given.

        Averaged across answers rather than across questions, so a question
        everyone skipped weighs as much as it should.
        """
        possible = sum(d.total for d in self.distributions)
        if possible == 0:
            return 0.0
        answered = sum(d.answered for d in self.distributions)
        return round(answered / possible * 100, 1)

    @property
    def lowest_response_rate(self) -> QuestionDistribution | None:
        """The question people skipped most.

        Worth surfacing on its own: a question with a low response rate is
        usually unclear or uncomfortable, and every statistic computed from
        it rests on fewer people than the reader assumes.
        """
        answerable = [d for d in self.distributions if d.total]
        if not answerable:
            return None
        return min(answerable, key=lambda d: d.response_rate)


def summarize(
    frame: pd.DataFrame, question_types: dict[str, str], scales: dict[str, list[str]] | None = None
) -> DatasetSummary:
    """Describe every question in a wide response frame.

    ``question_types`` maps column name to the inferred type, and ``scales``
    gives the answer order for ordinal questions. Both come from ingestion:
    the engine does not re-infer types, because the stored data and the
    analysis must agree on what a question is.
    """
    scales = scales or {}

    distributions = [
        _describe_column(
            position=position,
            text=str(column),
            column=frame[column],
            question_type=question_types.get(str(column), "categorical"),
            scale=scales.get(str(column), []),
        )
        for position, column in enumerate(frame.columns)
    ]

    return DatasetSummary(
        respondents=len(frame),
        questions=len(frame.columns),
        distributions=distributions,
    )


def _describe_column(
    position: int, text: str, column: pd.Series, question_type: str, scale: list[str]
) -> QuestionDistribution:
    """Describe one question."""
    answered = column.dropna()
    missing = len(column) - len(answered)

    return QuestionDistribution(
        position=position,
        text=text,
        type=question_type,
        counts=_count_values(answered, question_type, scale),
        answered=len(answered),
        missing=missing,
        numeric=_summarize_numeric(answered) if question_type == "numeric" else None,
    )


def _count_values(answered: pd.Series, question_type: str, scale: list[str]) -> list[ValueCount]:
    """Count each answer, ordered by whatever the question type makes useful."""
    if answered.empty:
        return []

    counts = answered.astype(str).value_counts()
    total = int(counts.sum())

    if question_type == "numeric":
        # A continuous column has no meaningful bar chart of raw values; the
        # numeric summary carries its shape instead.
        return []

    ordered = _order_counts(counts, question_type, scale)
    return _fold_long_tail(ordered, total)


def _order_counts(counts: pd.Series, question_type: str, scale: list[str]) -> pd.Series:
    """Order a distribution the way a reader expects to see it.

    Ordinal answers keep their scale order — a satisfaction chart running
    "Strongly disagree" to "Strongly agree" reads as a shape, while the same
    bars sorted by frequency read as noise. Everything else sorts by size,
    which puts the answer that matters first.
    """
    if question_type != "ordinal" or not scale:
        return counts

    lookup = {point.lower(): index for index, point in enumerate(scale)}
    known = [value for value in counts.index if str(value).lower() in lookup]
    unknown = [value for value in counts.index if str(value).lower() not in lookup]

    ordered_index = sorted(known, key=lambda v: lookup[str(v).lower()]) + unknown
    return counts.reindex(ordered_index)


def _fold_long_tail(counts: pd.Series, total: int) -> list[ValueCount]:
    """Turn counts into percentages, folding rare answers into one entry."""
    values = [
        ValueCount(value=str(value), count=int(count), percentage=round(count / total * 100, 1))
        for value, count in counts.items()
    ]

    if len(values) <= MAX_PLOTTED_CATEGORIES:
        return values

    head = values[: MAX_PLOTTED_CATEGORIES - 1]
    tail = values[MAX_PLOTTED_CATEGORIES - 1 :]

    return [
        *head,
        ValueCount(
            value=f"Other ({len(tail)} answers)",
            count=sum(v.count for v in tail),
            # Summed from the tail rather than recomputed, so the column adds
            # up to 100 instead of drifting by a rounding step per answer.
            percentage=round(sum(v.percentage for v in tail), 1),
        ),
    ]


def _summarize_numeric(answered: pd.Series) -> NumericSummary | None:
    """Summarize a numeric column, or None when it holds no numbers."""
    numbers = pd.to_numeric(answered, errors="coerce").dropna()
    if numbers.empty:
        return None

    return NumericSummary(
        mean=round(float(numbers.mean()), 2),
        median=round(float(numbers.median()), 2),
        # Sample standard deviation: these responses are a sample of a wider
        # population, not the population itself.
        std_dev=round(float(numbers.std(ddof=1)), 2) if len(numbers) > 1 else 0.0,
        minimum=round(float(numbers.min()), 2),
        maximum=round(float(numbers.max()), 2),
        q1=round(float(numbers.quantile(0.25)), 2),
        q3=round(float(numbers.quantile(0.75)), 2),
    )
