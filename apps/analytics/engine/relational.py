"""Relationships between pairs of survey questions.

Pure module (ADR 0001): DataFrames in, dataclasses out.

The statistics here are the ones most easily misused. A chi-square will
return a number for any two columns, significant or not, valid or not, and
reporting that number without its caveats is how survey tools produce
confident nonsense. Three guards are built in rather than left to the reader:

* **Expected-count validity.** Chi-square approximates a distribution that
  only holds when expected cell counts are large enough. Below that, the
  p-value is not trustworthy and the result says so.
* **Effect size alongside significance.** With enough respondents, trivial
  associations become "significant". Cramer's V says how strong the link is,
  which is the question anyone actually asked.
* **Multiple-comparison correction.** Testing 20 questions means 190 pairs;
  at p < 0.05 roughly 10 will look significant by chance alone. Benjamini-
  Hochberg controls that, and without it an exploratory tool manufactures
  findings.
"""

from dataclasses import dataclass
from enum import StrEnum

import pandas as pd
from scipy import stats

# Conventional threshold. Kept as a named constant because it appears in the
# correction as well, and the two must never drift apart.
SIGNIFICANCE_LEVEL = 0.05

# Chi-square assumes expected counts are not tiny. Cochran's rule: no cell
# below 1, and at most 20% of cells below 5.
MIN_EXPECTED_COUNT = 5
MAX_SMALL_CELL_SHARE = 0.2
ABSOLUTE_MIN_EXPECTED = 1

# Cramer's V cutoffs, following Cohen. Reported as words because "V = 0.21"
# means nothing to the person reading the dashboard.
STRENGTH_THRESHOLDS = ((0.1, "negligible"), (0.2, "weak"), (0.35, "moderate"))

# Free text has no categories to cross-tabulate, and a numeric column would
# produce a contingency table with one column per distinct value.
TESTABLE_TYPES = frozenset({"categorical", "ordinal"})


class Strength(StrEnum):
    NEGLIGIBLE = "negligible"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


@dataclass(frozen=True)
class ContingencyTable:
    """A cross-tabulation of two questions."""

    row_labels: list[str]
    column_labels: list[str]
    counts: list[list[int]]

    @property
    def total(self) -> int:
        return sum(sum(row) for row in self.counts)

    @property
    def row_totals(self) -> list[int]:
        return [sum(row) for row in self.counts]

    @property
    def column_totals(self) -> list[int]:
        return [sum(column) for column in zip(*self.counts, strict=True)]

    def row_percentages(self) -> list[list[float]]:
        """Each cell as a share of its row.

        Row percentages, not overall percentages: the readable finding is
        "68% of those who said X also said Y", which is a share within a
        row, and comparing raw counts across rows of different sizes is the
        most common way to misread one of these tables.
        """
        return [
            [round(cell / total * 100, 1) if total else 0.0 for cell in row]
            for row, total in zip(self.counts, self.row_totals, strict=True)
        ]


@dataclass(frozen=True)
class Association:
    """The measured relationship between two questions."""

    row_question: str
    column_question: str
    table: ContingencyTable
    chi_square: float
    p_value: float
    degrees_of_freedom: int
    cramers_v: float
    respondents: int
    # True when expected counts satisfy Cochran's rule.
    is_reliable: bool
    # Set once the whole set of pairs has been corrected together.
    adjusted_p_value: float | None = None

    @property
    def is_significant(self) -> bool:
        """Whether the association survives correction and its own assumptions.

        Deliberately strict: an unreliable test is not significant no matter
        how small its p-value, because that p-value was computed from an
        approximation that does not hold.
        """
        if not self.is_reliable:
            return False

        p = self.adjusted_p_value if self.adjusted_p_value is not None else self.p_value
        return p < SIGNIFICANCE_LEVEL

    @property
    def strength(self) -> Strength:
        """Effect size in words."""
        for threshold, label in STRENGTH_THRESHOLDS:
            if self.cramers_v < threshold:
                return Strength(label)
        return Strength.STRONG


def cross_tabulate(
    rows: pd.Series,
    columns: pd.Series,
    row_scale: list[str] | None = None,
    column_scale: list[str] | None = None,
) -> ContingencyTable:
    """Cross-tabulate two answer columns, dropping respondents missing either.

    Pairwise deletion: a respondent who skipped one of the two questions
    cannot contribute to their relationship, but still counts toward every
    other pair. Dropping them from the whole dataset instead would shrink
    every analysis to the people who answered everything.

    Ordinal answers are laid out in scale order. crosstab sorts labels
    alphabetically, which puts "Muy de acuerdo" between "En desacuerdo" and
    "Neutral" — a table whose columns run in an order nobody was asked the
    question in, and which hides the diagonal that makes a relationship
    visible at a glance.
    """
    paired = pd.DataFrame({"row": rows, "column": columns}).dropna()
    table = pd.crosstab(paired["row"], paired["column"])

    table = table.reindex(index=_ordered(table.index, row_scale))
    table = table.reindex(columns=_ordered(table.columns, column_scale))

    return ContingencyTable(
        row_labels=[str(label) for label in table.index],
        column_labels=[str(label) for label in table.columns],
        counts=table.to_numpy().tolist(),
    )


def _ordered(labels: pd.Index, scale: list[str] | None) -> list:
    """Lay labels out in scale order, keeping any the scale does not name.

    Unexpected answers are appended rather than dropped: an answer outside
    the scale is still a respondent, and silently removing it would change
    the totals the table reports.
    """
    if not scale:
        return list(labels)

    position = {point.lower(): index for index, point in enumerate(scale)}
    known = [label for label in labels if str(label).lower() in position]
    unknown = [label for label in labels if str(label).lower() not in position]

    return sorted(known, key=lambda label: position[str(label).lower()]) + unknown


def associate(
    row_question: str,
    column_question: str,
    rows: pd.Series,
    columns: pd.Series,
    row_scale: list[str] | None = None,
    column_scale: list[str] | None = None,
) -> Association | None:
    """Measure the association between two questions.

    Returns None when there is nothing to test — a question with a single
    answer has no variation, and a table with one row or column has no
    relationship to measure.
    """
    table = cross_tabulate(rows, columns, row_scale, column_scale)

    if len(table.row_labels) < 2 or len(table.column_labels) < 2:
        return None

    observed = pd.DataFrame(table.counts)
    # correction=False: Yates' continuity correction applies only to 2x2
    # tables, so leaving it on would make a 2x2 result incomparable with
    # every other pair in the same list. It is also widely held to be
    # over-conservative.
    chi2, p_value, dof, expected = stats.chi2_contingency(observed, correction=False)

    return Association(
        row_question=row_question,
        column_question=column_question,
        table=table,
        chi_square=round(float(chi2), 4),
        p_value=float(p_value),
        degrees_of_freedom=int(dof),
        cramers_v=_cramers_v(float(chi2), table),
        respondents=table.total,
        is_reliable=_is_reliable(expected),
    )


def analyze(
    frame: pd.DataFrame,
    question_types: dict[str, str],
    scales: dict[str, list[str]] | None = None,
) -> list[Association]:
    """Measure every testable pair of questions in a dataset.

    Results come back strongest first, and their p-values are corrected
    together — the correction is only meaningful across the whole family of
    tests, which is why pairs cannot be analyzed one at a time.
    """
    scales = scales or {}
    testable = [
        column for column in frame.columns if question_types.get(str(column)) in TESTABLE_TYPES
    ]

    associations = [
        association
        for index, row_question in enumerate(testable)
        for column_question in testable[index + 1 :]
        if (
            association := associate(
                str(row_question),
                str(column_question),
                frame[row_question],
                frame[column_question],
                scales.get(str(row_question)),
                scales.get(str(column_question)),
            )
        )
        is not None
    ]

    corrected = adjust_p_values(associations)
    return sorted(corrected, key=lambda a: (-a.cramers_v, a.p_value))


def adjust_p_values(associations: list[Association]) -> list[Association]:
    """Control the false discovery rate across a family of tests.

    Benjamini-Hochberg rather than Bonferroni: this is exploratory analysis,
    where the cost of missing a real pattern is higher than the cost of one
    false lead. Bonferroni would control the chance of *any* false positive
    and, across a hundred pairs, leave almost nothing standing.

    The procedure sorts p-values ascending and scales each by n/rank, then
    enforces monotonicity so a weaker result can never end up with a smaller
    adjusted value than a stronger one.
    """
    if not associations:
        return []

    count = len(associations)
    ordered = sorted(range(count), key=lambda i: associations[i].p_value)

    adjusted = [0.0] * count
    running_minimum = 1.0

    for position in reversed(range(count)):
        index = ordered[position]
        scaled = associations[index].p_value * count / (position + 1)
        running_minimum = min(running_minimum, scaled, 1.0)
        adjusted[index] = running_minimum

    return [
        _replace_adjusted(association, adjusted[index])
        for index, association in enumerate(associations)
    ]


def _replace_adjusted(association: Association, adjusted: float) -> Association:
    """Return a copy carrying its corrected p-value."""
    return Association(
        row_question=association.row_question,
        column_question=association.column_question,
        table=association.table,
        chi_square=association.chi_square,
        p_value=association.p_value,
        degrees_of_freedom=association.degrees_of_freedom,
        cramers_v=association.cramers_v,
        respondents=association.respondents,
        is_reliable=association.is_reliable,
        adjusted_p_value=round(adjusted, 6),
    )


def _cramers_v(chi_square: float, table: ContingencyTable) -> float:
    """Effect size, on a 0-1 scale independent of sample size.

    Chi-square grows with the number of respondents, so it cannot be compared
    between datasets or used to rank findings. Dividing it out is what makes
    "which relationship is strongest" answerable.
    """
    total = table.total
    smaller_dimension = min(len(table.row_labels), len(table.column_labels)) - 1

    if total == 0 or smaller_dimension < 1:
        return 0.0

    return round(float((chi_square / (total * smaller_dimension)) ** 0.5), 4)


def _is_reliable(expected: object) -> bool:
    """Whether expected counts satisfy Cochran's rule.

    Below this the chi-square approximation breaks down and its p-value stops
    meaning what it appears to mean. The result is still shown — hiding it
    would be its own distortion — but flagged as unreliable.
    """
    cells = pd.DataFrame(expected).to_numpy().flatten()

    if (cells < ABSOLUTE_MIN_EXPECTED).any():
        return False

    small_share = (cells < MIN_EXPECTED_COUNT).sum() / len(cells)
    return bool(small_share <= MAX_SMALL_CELL_SHARE)
