"""Tests for the relational engine.

Chi-square is the statistic in this project most likely to be quietly wrong,
because it returns a plausible number for any input. Every expected value
below is worked out by hand in the docstring so a broken formula fails
instead of looking reasonable.
"""

import pandas as pd
import pytest

from apps.analytics.engine.relational import (
    SIGNIFICANCE_LEVEL,
    Strength,
    adjust_p_values,
    analyze,
    associate,
    cross_tabulate,
)


def paired(rows: list[str], columns: list[str]) -> tuple[pd.Series, pd.Series]:
    return pd.Series(rows), pd.Series(columns)


def build(counts: dict[tuple[str, str], int]) -> tuple[pd.Series, pd.Series]:
    """Expand a cell-count mapping into two aligned answer columns."""
    rows: list[str] = []
    columns: list[str] = []
    for (row_value, column_value), count in counts.items():
        rows.extend([row_value] * count)
        columns.extend([column_value] * count)
    return pd.Series(rows), pd.Series(columns)


class TestCrossTabulation:
    def test_counts_land_in_the_right_cells(self) -> None:
        rows, columns = build({("Sales", "Yes"): 3, ("Sales", "No"): 1, ("Support", "Yes"): 2})

        table = cross_tabulate(rows, columns)

        assert table.row_labels == ["Sales", "Support"]
        assert table.column_labels == ["No", "Yes"]
        assert table.counts == [[1, 3], [0, 2]]
        assert table.total == 6

    def test_totals_are_computed_both_ways(self) -> None:
        rows, columns = build({("A", "X"): 2, ("A", "Y"): 3, ("B", "X"): 4, ("B", "Y"): 1})

        table = cross_tabulate(rows, columns)

        assert table.row_totals == [5, 5]
        assert table.column_totals == [6, 4]

    def test_row_percentages_are_shares_within_each_row(self) -> None:
        """The readable finding is "68% of those who said X also said Y".

        That is a share within a row. Comparing raw counts across rows of
        different sizes is the most common way to misread these tables.
        """
        rows, columns = build(
            {
                ("Unsatisfied", "Low"): 17,
                ("Unsatisfied", "High"): 8,
                ("Satisfied", "Low"): 5,
                ("Satisfied", "High"): 20,
            }
        )

        table = cross_tabulate(rows, columns)

        # Satisfied row: 20 High of 25 = 80.0%, 5 Low of 25 = 20.0%
        satisfied = table.row_labels.index("Satisfied")
        assert table.row_percentages()[satisfied] == [80.0, 20.0]

    def test_respondents_missing_either_answer_are_dropped_pairwise(self) -> None:
        """Someone who skipped one question cannot inform this pair, but must
        still count toward every other pair.
        """
        rows = pd.Series(["A", "A", "B", None, "B"])
        columns = pd.Series(["X", None, "Y", "Y", "X"])

        table = cross_tabulate(rows, columns)

        assert table.total == 3


class TestScaleOrder:
    def test_ordinal_answers_are_laid_out_in_scale_order(self) -> None:
        """crosstab sorts labels alphabetically, which puts "Muy de acuerdo"
        between "En desacuerdo" and "Neutral" — a table running in an order
        nobody was asked the question in, hiding the diagonal that makes a
        relationship visible at a glance.
        """
        scale = ["muy en desacuerdo", "en desacuerdo", "neutral", "de acuerdo", "muy de acuerdo"]
        rows, columns = build(
            {
                ("Soporte", "Muy en desacuerdo"): 20,
                ("Soporte", "En desacuerdo"): 10,
                ("Ingeniería", "Muy de acuerdo"): 20,
                ("Ingeniería", "De acuerdo"): 10,
                ("Ventas", "Neutral"): 20,
            }
        )

        table = cross_tabulate(rows, columns, column_scale=scale)

        assert table.column_labels == [
            "Muy en desacuerdo",
            "En desacuerdo",
            "Neutral",
            "De acuerdo",
            "Muy de acuerdo",
        ]

    def test_an_answer_outside_the_scale_is_kept_at_the_end(self) -> None:
        """Dropping it would silently change the totals the table reports."""
        rows, columns = build(
            {("A", "Agree"): 20, ("A", "Not applicable"): 10, ("B", "Disagree"): 20}
        )

        table = cross_tabulate(rows, columns, column_scale=["disagree", "agree"])

        assert table.column_labels == ["Disagree", "Agree", "Not applicable"]
        assert table.total == 50

    def test_analyze_threads_the_scales_through(self) -> None:
        frame = pd.DataFrame(
            {
                "Team": ["Soporte"] * 30 + ["Ingeniería"] * 30,
                "Mood": ["Muy en desacuerdo"] * 30 + ["Muy de acuerdo"] * 30,
            }
        )
        types = {"Team": "categorical", "Mood": "ordinal"}
        scales = {"Mood": ["muy en desacuerdo", "neutral", "muy de acuerdo"]}

        result = analyze(frame, types, scales)[0]

        assert result.table.column_labels == ["Muy en desacuerdo", "Muy de acuerdo"]


class TestChiSquare:
    def test_statistic_matches_the_hand_computed_value(self) -> None:
        """Table:
                   B1   B2  | total
            A1     10   20  |   30
            A2     30   20  |   50
            total  40   40  |   80

        Expected = row_total * col_total / n:
            A1B1 = 30*40/80 = 15    A1B2 = 15
            A2B1 = 50*40/80 = 25    A2B2 = 25

        chi2 = (10-15)^2/15 + (20-15)^2/15 + (30-25)^2/25 + (20-25)^2/25
             = 25/15 + 25/15 + 25/25 + 25/25
             = 1.6667 + 1.6667 + 1 + 1
             = 5.3333

        dof = (2-1)(2-1) = 1

        Yates' correction is off, so this matches the textbook formula. With
        it on, scipy would return 4.32 and a 2x2 result would be incomparable
        with every other pair in the same list.
        """
        rows, columns = build(
            {("A1", "B1"): 10, ("A1", "B2"): 20, ("A2", "B1"): 30, ("A2", "B2"): 20}
        )

        result = associate("A", "B", rows, columns)

        assert result.chi_square == pytest.approx(5.3333, abs=0.0001)
        assert result.degrees_of_freedom == 1
        assert result.respondents == 80

    def test_cramers_v_matches_the_hand_computed_value(self) -> None:
        """From the table above: chi2 = 5.3333, n = 80, min(r-1, c-1) = 1.

        V = sqrt(chi2 / (n * min(r-1, c-1)))
          = sqrt(5.3333 / 80)
          = sqrt(0.066667)
          = 0.2582
        """
        rows, columns = build(
            {("A1", "B1"): 10, ("A1", "B2"): 20, ("A2", "B1"): 30, ("A2", "B2"): 20}
        )

        result = associate("A", "B", rows, columns)

        assert result.cramers_v == pytest.approx(0.2582, abs=0.0001)

    def test_perfect_independence_yields_zero(self) -> None:
        """Every cell equals its expected count, so there is no deviation.

            B1  B2
        A1  10  10
        A2  10  10
        """
        rows, columns = build(
            {("A1", "B1"): 10, ("A1", "B2"): 10, ("A2", "B1"): 10, ("A2", "B2"): 10}
        )

        result = associate("A", "B", rows, columns)

        assert result.chi_square == 0.0
        assert result.cramers_v == 0.0
        assert result.p_value == pytest.approx(1.0)
        assert result.is_significant is False

    def test_a_perfect_relationship_is_detected(self) -> None:
        """Everyone in Sales said Yes and everyone in Support said No."""
        rows, columns = build({("Sales", "Yes"): 40, ("Support", "No"): 40})

        result = associate("Team", "Answer", rows, columns)

        assert result.cramers_v == 1.0
        assert result.strength is Strength.STRONG
        assert result.is_significant is True

    def test_degrees_of_freedom_follow_the_table_shape(self) -> None:
        """A 3x2 table has (3-1)(2-1) = 2 degrees of freedom."""
        rows, columns = build(
            {
                ("A", "X"): 10,
                ("A", "Y"): 5,
                ("B", "X"): 8,
                ("B", "Y"): 12,
                ("C", "X"): 6,
                ("C", "Y"): 9,
            }
        )

        result = associate("Q1", "Q2", rows, columns)

        assert result.degrees_of_freedom == 2


class TestReliability:
    def test_a_table_with_adequate_expected_counts_is_reliable(self) -> None:
        rows, columns = build(
            {("A1", "B1"): 10, ("A1", "B2"): 20, ("A2", "B1"): 30, ("A2", "B2"): 20}
        )

        assert associate("A", "B", rows, columns).is_reliable is True

    def test_tiny_expected_counts_make_the_test_unreliable(self) -> None:
        """Cochran's rule: expected counts this small break the chi-square
        approximation, so its p-value stops meaning what it appears to mean.
        """
        rows, columns = build({("A1", "B1"): 1, ("A1", "B2"): 1, ("A2", "B1"): 1, ("A2", "B2"): 2})

        result = associate("A", "B", rows, columns)

        assert result.is_reliable is False

    def test_an_unreliable_result_is_never_reported_as_significant(self) -> None:
        """Strict on purpose: the p-value came from an approximation that
        does not hold, so a small one proves nothing.
        """
        rows, columns = build({("A1", "B1"): 3, ("A2", "B2"): 3})

        result = associate("A", "B", rows, columns)

        assert result.p_value < SIGNIFICANCE_LEVEL
        assert result.is_reliable is False
        assert result.is_significant is False


class TestStrengthLabels:
    @pytest.mark.parametrize(
        ("cramers_v", "expected"),
        [
            (0.05, Strength.NEGLIGIBLE),
            (0.15, Strength.WEAK),
            (0.30, Strength.MODERATE),
            (0.50, Strength.STRONG),
        ],
    )
    def test_effect_size_is_reported_in_words(self, cramers_v: float, expected: Strength) -> None:
        """ "V = 0.21" means nothing to the person reading the dashboard."""
        rows, columns = build({("A", "X"): 10, ("B", "Y"): 10})
        result = associate("A", "B", rows, columns)

        relabelled = type(result)(**{**result.__dict__, "cramers_v": cramers_v})

        assert relabelled.strength is expected


class TestDegenerateInput:
    def test_a_question_with_one_answer_has_nothing_to_measure(self) -> None:
        """No variation means no relationship, not a relationship of zero."""
        rows, columns = paired(["Yes"] * 10, ["A", "B"] * 5)

        assert associate("Q1", "Q2", rows, columns) is None

    def test_no_overlapping_respondents_yields_nothing(self) -> None:
        rows = pd.Series(["A", "B", None, None])
        columns = pd.Series([None, None, "X", "Y"])

        assert associate("Q1", "Q2", rows, columns) is None


class TestEffectSizeGuards:
    def test_a_degenerate_table_has_no_effect_size(self) -> None:
        """Cramer's V divides by min(rows, columns) - 1.

        A table with a single row or column makes that zero. associate()
        rejects such tables before reaching here, but the guard has to hold
        on its own: the next caller may not be as careful.
        """
        from apps.analytics.engine.relational import ContingencyTable, _cramers_v

        single_column = ContingencyTable(
            row_labels=["a", "b"], column_labels=["x"], counts=[[5], [5]]
        )

        assert _cramers_v(chi_square=10.0, table=single_column) == 0.0

    def test_an_empty_table_has_no_effect_size(self) -> None:
        """Zero respondents would divide by zero."""
        from apps.analytics.engine.relational import ContingencyTable, _cramers_v

        empty = ContingencyTable(
            row_labels=["a", "b"], column_labels=["x", "y"], counts=[[0, 0], [0, 0]]
        )

        assert _cramers_v(chi_square=0.0, table=empty) == 0.0


class TestMultipleComparisonCorrection:
    def test_adjusted_values_follow_benjamini_hochberg(self) -> None:
        """p-values 0.01, 0.02, 0.03, 0.04 over n = 4 tests.

        Adjusted = p * n / rank, then made monotone from the largest down:
            rank 4: 0.04 * 4/4 = 0.04
            rank 3: 0.03 * 4/3 = 0.04
            rank 2: 0.02 * 4/2 = 0.04
            rank 1: 0.01 * 4/1 = 0.04
        """
        associations = [_association_with_p(p) for p in (0.01, 0.02, 0.03, 0.04)]

        adjusted = adjust_p_values(associations)

        assert [a.adjusted_p_value for a in adjusted] == [0.04, 0.04, 0.04, 0.04]

    def test_adjustment_is_monotone(self) -> None:
        """p-values 0.001 and 0.5 over n = 2:
            rank 2: 0.5   * 2/2 = 0.5
            rank 1: 0.001 * 2/1 = 0.002

        A weaker result must never end up with a smaller adjusted value than
        a stronger one.
        """
        adjusted = adjust_p_values([_association_with_p(0.001), _association_with_p(0.5)])

        assert adjusted[0].adjusted_p_value == 0.002
        assert adjusted[1].adjusted_p_value == 0.5

    def test_adjusted_values_never_exceed_one(self) -> None:
        adjusted = adjust_p_values([_association_with_p(0.9) for _ in range(10)])

        assert all(a.adjusted_p_value <= 1.0 for a in adjusted)

    def test_a_marginal_result_stops_being_significant_after_correction(self) -> None:
        """p = 0.04 alone passes; as one of 20 tests it should not.

        Adjusted = 0.04 * 20/1 = 0.8. Without this, an exploratory tool
        manufactures roughly one finding per twenty pairs from noise alone.
        """
        associations = [_association_with_p(0.04), *[_association_with_p(0.9)] * 19]

        adjusted = adjust_p_values(associations)

        assert adjusted[0].p_value < SIGNIFICANCE_LEVEL
        assert adjusted[0].adjusted_p_value == pytest.approx(0.8)
        assert adjusted[0].is_significant is False

    def test_an_empty_family_needs_no_correction(self) -> None:
        assert adjust_p_values([]) == []


class TestAnalyze:
    def test_every_testable_pair_is_measured_once(self) -> None:
        """Three categorical questions make three pairs, not six or nine."""
        frame = pd.DataFrame(
            {
                "Q1": ["a", "b"] * 20,
                "Q2": ["x", "y"] * 20,
                "Q3": ["p", "q"] * 20,
            }
        )
        types = dict.fromkeys(["Q1", "Q2", "Q3"], "categorical")

        results = analyze(frame, types)

        assert len(results) == 3
        pairs = {(r.row_question, r.column_question) for r in results}
        assert pairs == {("Q1", "Q2"), ("Q1", "Q3"), ("Q2", "Q3")}

    def test_free_text_and_numeric_questions_are_excluded(self) -> None:
        """Free text has no categories; a numeric column would produce one
        table column per distinct value.
        """
        frame = pd.DataFrame(
            {
                "Category": ["a", "b"] * 20,
                "Rating": ["1", "2"] * 20,
                "Age": [str(n) for n in range(40)],
                "Comment": [f"comment {n}" for n in range(40)],
            }
        )
        types = {
            "Category": "categorical",
            "Rating": "ordinal",
            "Age": "numeric",
            "Comment": "free_text",
        }

        results = analyze(frame, types)

        assert len(results) == 1
        assert {results[0].row_question, results[0].column_question} == {"Category", "Rating"}

    def test_results_are_ordered_by_effect_size(self) -> None:
        """Strongest first: with dozens of pairs, ranking by p-value would
        put the largest sample on top rather than the biggest finding.
        """
        frame = pd.DataFrame(
            {
                "Team": ["Sales"] * 20 + ["Support"] * 20,
                "Mirror": ["Yes"] * 20 + ["No"] * 20,
                "Noise": ["Yes", "No"] * 20,
            }
        )
        types = dict.fromkeys(["Team", "Mirror", "Noise"], "categorical")

        results = analyze(frame, types)

        assert results[0].cramers_v == 1.0
        assert [r.cramers_v for r in results] == sorted(
            [r.cramers_v for r in results], reverse=True
        )

    def test_a_dataset_with_one_testable_question_yields_nothing(self) -> None:
        frame = pd.DataFrame({"Only": ["a", "b"] * 10, "Age": ["1", "2"] * 10})

        assert analyze(frame, {"Only": "categorical", "Age": "numeric"}) == []


def _association_with_p(p_value: float):
    """An association carrying only the p-value the correction reads."""
    from apps.analytics.engine.relational import Association, ContingencyTable

    return Association(
        row_question="A",
        column_question="B",
        table=ContingencyTable(row_labels=["a"], column_labels=["b"], counts=[[1]]),
        chi_square=1.0,
        p_value=p_value,
        degrees_of_freedom=1,
        cramers_v=0.1,
        respondents=100,
        is_reliable=True,
    )
