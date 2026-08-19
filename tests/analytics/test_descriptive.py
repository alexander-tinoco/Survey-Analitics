"""Tests for the descriptive engine.

Every expected value here is computed by hand and written into the assertion.
Deriving expectations with the same library the code uses would only prove
pandas agrees with itself; a wrong formula would pass. These numbers fail
loudly instead.

No database: the engine takes a DataFrame, so a test is a literal.
"""

import pandas as pd

from apps.analytics.engine.descriptive import (
    MAX_PLOTTED_CATEGORIES,
    NumericSummary,
    summarize,
)


class TestCounts:
    def test_counts_and_percentages_are_computed_per_answer(self) -> None:
        """8 answers: 4 Sales, 2 Support, 2 Engineering.

        By hand: 4/8 = 50.0%, 2/8 = 25.0%, 2/8 = 25.0%.
        """
        frame = pd.DataFrame({"Team": ["Sales"] * 4 + ["Support"] * 2 + ["Engineering"] * 2})

        distribution = summarize(frame, {"Team": "categorical"}).distributions[0]

        assert [(c.value, c.count, c.percentage) for c in distribution.counts] == [
            ("Sales", 4, 50.0),
            ("Support", 2, 25.0),
            ("Engineering", 2, 25.0),
        ]

    def test_categorical_answers_are_ordered_by_frequency(self) -> None:
        """The answer that matters most should be read first."""
        frame = pd.DataFrame({"Team": ["A", "B", "B", "B", "C", "C"]})

        distribution = summarize(frame, {"Team": "categorical"}).distributions[0]

        assert [c.value for c in distribution.counts] == ["B", "C", "A"]
        assert distribution.modal_answer == "B"

    def test_percentages_are_computed_over_answers_not_respondents(self) -> None:
        """3 of 5 answered: 2 Yes and 1 No are 66.7% and 33.3%, not 40/20.

        A percentage of respondents would silently understate every option
        whenever anyone skipped the question.
        """
        frame = pd.DataFrame({"Q": ["Yes", "Yes", "No", None, None]})

        distribution = summarize(frame, {"Q": "categorical"}).distributions[0]

        assert distribution.answered == 3
        assert distribution.missing == 2
        assert [(c.value, c.percentage) for c in distribution.counts] == [
            ("Yes", 66.7),
            ("No", 33.3),
        ]


class TestOrdinalOrdering:
    def test_ordinal_answers_keep_their_scale_order(self) -> None:
        """A satisfaction chart must read low-to-high, not most-to-least.

        Sorted by frequency these same bars would appear as Agree, Neutral,
        Disagree — an ordering that hides whether opinion leans positive.
        """
        frame = pd.DataFrame({"Satisfaction": ["Agree"] * 4 + ["Disagree"] * 2 + ["Neutral"] * 3})
        scale = {"Satisfaction": ["disagree", "neutral", "agree"]}

        distribution = summarize(frame, {"Satisfaction": "ordinal"}, scales=scale).distributions[0]

        assert [c.value for c in distribution.counts] == ["Disagree", "Neutral", "Agree"]
        assert [c.count for c in distribution.counts] == [2, 3, 4]

    def test_an_answer_outside_the_scale_is_kept_at_the_end(self) -> None:
        """Unexpected answers are shown, not silently dropped."""
        frame = pd.DataFrame({"Q": ["Agree", "Disagree", "Not applicable", "Agree"]})

        distribution = summarize(
            frame, {"Q": "ordinal"}, scales={"Q": ["disagree", "agree"]}
        ).distributions[0]

        assert [c.value for c in distribution.counts] == ["Disagree", "Agree", "Not applicable"]


class TestNumericSummary:
    def test_summary_statistics_match_hand_computed_values(self) -> None:
        """Values 1..5.

        mean   = 15/5 = 3
        median = 3
        var    = ((-2)^2+(-1)^2+0+1^2+2^2)/(5-1) = 10/4 = 2.5
        std    = sqrt(2.5) = 1.5811... -> 1.58
        q1     = 2, q3 = 4  (linear interpolation over 5 points)
        """
        frame = pd.DataFrame({"Age": [1, 2, 3, 4, 5]})

        summary = summarize(frame, {"Age": "numeric"}).distributions[0].numeric

        assert summary == NumericSummary(
            mean=3.0, median=3.0, std_dev=1.58, minimum=1.0, maximum=5.0, q1=2.0, q3=4.0
        )

    def test_standard_deviation_uses_the_sample_formula(self) -> None:
        """Values 2,4,4,4,5,5,7,9 — the textbook example.

        mean = 40/8 = 5
        squared deviations: 9,1,1,1,0,0,4,16 -> sum 32
        population std = sqrt(32/8) = 2.0
        sample std     = sqrt(32/7) = 2.1380... -> 2.14

        Survey responses are a sample, so the sample formula is correct here.
        Using the population formula would understate every spread.
        """
        frame = pd.DataFrame({"Score": [2, 4, 4, 4, 5, 5, 7, 9]})

        summary = summarize(frame, {"Score": "numeric"}).distributions[0].numeric

        assert summary.mean == 5.0
        assert summary.std_dev == 2.14

    def test_a_single_answer_has_no_spread(self) -> None:
        """One value cannot have a sample deviation; report zero, not NaN."""
        frame = pd.DataFrame({"Age": [42]})

        summary = summarize(frame, {"Age": "numeric"}).distributions[0].numeric

        assert summary.mean == 42.0
        assert summary.std_dev == 0.0

    def test_numeric_questions_report_no_bar_chart(self) -> None:
        """Continuous values have no meaningful bars; the summary carries them."""
        frame = pd.DataFrame({"Age": [23, 31, 45, 52, 38]})

        distribution = summarize(frame, {"Age": "numeric"}).distributions[0]

        assert distribution.counts == []
        assert distribution.numeric is not None

    def test_a_column_with_no_numbers_yields_no_summary(self) -> None:
        frame = pd.DataFrame({"Age": ["unknown", "unknown"]})

        assert summarize(frame, {"Age": "numeric"}).distributions[0].numeric is None


class TestSkew:
    def test_a_symmetric_distribution_is_not_flagged(self) -> None:
        """1..5: mean and median are both 3, so the gap is zero."""
        frame = pd.DataFrame({"Q": [1, 2, 3, 4, 5]})

        summary = summarize(frame, {"Q": "numeric"}).distributions[0].numeric

        assert summary.is_skewed is False

    def test_an_outlier_pulling_the_mean_is_flagged(self) -> None:
        """1,1,1,1,100: median stays 1 while the mean jumps to 20.8.

        The gap is what tells a reader the mean is not describing a typical
        respondent, which is exactly when quoting the mean alone misleads.
        """
        frame = pd.DataFrame({"Q": [1, 1, 1, 1, 100]})

        summary = summarize(frame, {"Q": "numeric"}).distributions[0].numeric

        assert summary.median == 1.0
        assert summary.mean == 20.8
        assert summary.is_skewed is True

    def test_no_spread_means_no_skew(self) -> None:
        """Identical answers cannot be skewed, and must not divide by zero."""
        frame = pd.DataFrame({"Q": [7, 7, 7]})

        summary = summarize(frame, {"Q": "numeric"}).distributions[0].numeric

        assert summary.std_dev == 0.0
        assert summary.is_skewed is False


class TestResponseRates:
    def test_response_rate_is_answered_over_total(self) -> None:
        """3 answered of 4 = 75.0%."""
        frame = pd.DataFrame({"Q": ["a", "b", "c", None]})

        distribution = summarize(frame, {"Q": "categorical"}).distributions[0]

        assert distribution.response_rate == 75.0

    def test_overall_rate_averages_over_answers_not_questions(self) -> None:
        """2 questions x 4 respondents = 8 possible answers.

        Q1 answered 4, Q2 answered 1 -> 5/8 = 62.5%.

        Averaging the two question rates instead would give
        (100 + 25) / 2 = 62.5 here by coincidence, but diverges as soon as
        the questions have different response counts.
        """
        frame = pd.DataFrame({"Q1": ["a", "b", "c", "d"], "Q2": ["x", None, None, None]})

        summary = summarize(frame, {"Q1": "categorical", "Q2": "categorical"})

        assert summary.overall_response_rate == 62.5

    def test_the_most_skipped_question_is_identified(self) -> None:
        """A low response rate is a finding: the question was unclear or
        uncomfortable, and its statistics rest on fewer people than assumed.
        """
        frame = pd.DataFrame(
            {
                "Easy": ["a", "b", "c", "d"],
                "Awkward": ["x", None, None, None],
                "Middling": ["p", "q", None, None],
            }
        )
        types = dict.fromkeys(["Easy", "Awkward", "Middling"], "categorical")

        summary = summarize(frame, types)

        assert summary.lowest_response_rate.text == "Awkward"
        assert summary.lowest_response_rate.response_rate == 25.0

    def test_a_question_nobody_was_asked_reports_zero(self) -> None:
        """A dataset with no respondents has no rate to report.

        Reached when a dataset is created but its rows fail to ingest: the
        division would be zero over zero.
        """
        frame = pd.DataFrame({"Q": pd.Series([], dtype=object)})

        distribution = summarize(frame, {"Q": "categorical"}).distributions[0]

        assert distribution.total == 0
        assert distribution.response_rate == 0.0

    def test_an_entirely_unanswered_question_reports_zero(self) -> None:
        frame = pd.DataFrame({"Q": [None, None, None]})

        distribution = summarize(frame, {"Q": "categorical"}).distributions[0]

        assert distribution.answered == 0
        assert distribution.response_rate == 0.0
        assert distribution.modal_answer is None


class TestLongTail:
    def test_rare_answers_are_folded_into_one_entry(self) -> None:
        """20 options must not become 20 unreadable bars.

        The tail is folded, not dropped: its respondents still appear in the
        chart and the percentages still total 100.
        """
        options = [f"opt{i}" for i in range(20)]
        frame = pd.DataFrame({"Q": options * 2})

        counts = summarize(frame, {"Q": "categorical"}).distributions[0].counts

        assert len(counts) == MAX_PLOTTED_CATEGORIES
        assert counts[-1].value.startswith("Other")
        assert sum(c.count for c in counts) == 40
        assert round(sum(c.percentage for c in counts)) == 100

    def test_a_short_distribution_is_left_alone(self) -> None:
        frame = pd.DataFrame({"Q": ["a", "b", "c"]})

        counts = summarize(frame, {"Q": "categorical"}).distributions[0].counts

        assert len(counts) == 3
        assert not any(c.value.startswith("Other") for c in counts)


class TestDatasetShape:
    def test_summary_reports_the_dataset_dimensions(self) -> None:
        frame = pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]})

        summary = summarize(frame, {"A": "numeric", "B": "categorical"})

        assert summary.respondents == 3
        assert summary.questions == 2
        assert len(summary.distributions) == 2

    def test_questions_keep_their_column_order(self) -> None:
        frame = pd.DataFrame({"First": [1], "Second": [2], "Third": [3]})

        summary = summarize(frame, dict.fromkeys(["First", "Second", "Third"], "numeric"))

        assert [d.position for d in summary.distributions] == [0, 1, 2]
        assert [d.text for d in summary.distributions] == ["First", "Second", "Third"]

    def test_an_empty_dataset_does_not_divide_by_zero(self) -> None:
        summary = summarize(pd.DataFrame(), {})

        assert summary.respondents == 0
        assert summary.overall_response_rate == 0.0
        assert summary.lowest_response_rate is None
