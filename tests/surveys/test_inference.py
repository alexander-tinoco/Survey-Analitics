"""Tests for question type inference.

Type inference decides which statistical tests a question is eligible for, so
a wrong answer here does not crash anything — it silently produces findings
that mean nothing. Every case is a hand-written column with a known answer.
"""

import pandas as pd
import pytest

from apps.surveys.services.inference import (
    InferredType,
    is_missing,
    normalize_answer,
    profile_frame,
)


def profile_of(values: list[object], name: str = "Q1"):
    """Profile a single column."""
    return profile_frame(pd.DataFrame({name: values}))[0]


class TestNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  Agree  ", "Agree"),
            ("Strongly    Agree", "Strongly Agree"),
            ("Agree\n", "Agree"),
            (None, ""),
            (float("nan"), ""),
            (42, "42"),
        ],
    )
    def test_answers_are_collapsed_to_a_comparable_form(self, raw: object, expected: str) -> None:
        """Answers differing only by spacing are the same answer.

        Left alone, "Agree" and "Agree " become two categories and split a
        distribution that should have been one bar.
        """
        assert normalize_answer(raw) == expected

    @pytest.mark.parametrize("token", ["", "N/A", "n/a", "none", "-", "Prefer not to say"])
    def test_non_answers_are_recognized_as_missing(self, token: str) -> None:
        assert is_missing(token) is True

    @pytest.mark.parametrize("answer", ["Agree", "0", "No"])
    def test_real_answers_are_not_missing(self, answer: str) -> None:
        """'0' and 'No' are answers, not absences.

        Treating them as missing would delete the very responses that carry
        the negative signal.
        """
        assert is_missing(answer) is False


class TestNumericInference:
    def test_continuous_numbers_are_numeric(self) -> None:
        profile = profile_of([23.5, 41.2, 38.9, 55.1, 29.7, 61.3, 44.8])

        assert profile.type is InferredType.NUMERIC

    def test_many_distinct_whole_numbers_are_numeric(self) -> None:
        """Age in years is a measurement, not a rating."""
        profile = profile_of([23, 41, 38, 55, 29, 61, 44, 33, 27, 50, 46, 39])

        assert profile.type is InferredType.NUMERIC

    def test_a_five_point_rating_is_ordinal(self) -> None:
        """1-5 has an order and only five rungs: it is a scale, not a measure."""
        profile = profile_of([1, 5, 3, 4, 2, 5, 1, 3, 4, 2])

        assert profile.type is InferredType.ORDINAL
        assert profile.scale == ["1", "2", "3", "4", "5"]

    def test_a_zero_to_ten_recommendation_score_is_ordinal(self) -> None:
        """NPS is anchored at 0 and tops out at 10."""
        profile = profile_of([0, 7, 9, 10, 6, 8, 9, 10, 3])

        assert profile.type is InferredType.ORDINAL

    def test_a_handful_of_ages_is_not_mistaken_for_a_scale(self) -> None:
        """Five distinct whole numbers, but they start at 29.

        Counting distinct values alone would call this a five-point scale and
        replace real ages with ranks 1 to 5, destroying the actual data.
        """
        profile = profile_of([34, 29, 45, 38, 52])

        assert profile.type is InferredType.NUMERIC
        assert profile.scale == []


class TestDirtyNumericColumns:
    def test_a_stray_word_does_not_turn_an_age_column_into_prose(self) -> None:
        """One typed "unknown" must not discard seven valid ages.

        Requiring every value to parse would classify the column as free text,
        excluding it from analysis entirely over a single bad cell.
        """
        profile = profile_of([34, 29, 45, 38, 52, 61, 27, "unknown"])

        assert profile.type is InferredType.NUMERIC

    def test_a_genuinely_mixed_column_is_not_numeric(self) -> None:
        """Half numbers and half words is not a number column."""
        profile = profile_of([34, "Sales", 29, "Support", 45, "Sales"])

        assert profile.type is not InferredType.NUMERIC


class TestTextInference:
    def test_a_known_likert_scale_is_ordinal(self) -> None:
        """Agreement has direction; a chi-square alone would discard it."""
        profile = profile_of(
            ["Agree", "Strongly agree", "Neutral", "Disagree", "Agree", "Strongly disagree"]
        )

        assert profile.type is InferredType.ORDINAL
        assert profile.scale == [
            "strongly disagree",
            "disagree",
            "neutral",
            "agree",
            "strongly agree",
        ]

    def test_a_partially_used_scale_keeps_the_scale_order(self) -> None:
        """Nobody picked the extremes; the remaining points are still ordered."""
        profile = profile_of(["Agree", "Neutral", "Disagree", "Agree", "Neutral"])

        assert profile.type is InferredType.ORDINAL
        assert profile.scale == ["disagree", "neutral", "agree"]

    def test_unordered_options_are_categorical(self) -> None:
        """Departments have no order, so no rank should be invented for them."""
        profile = profile_of(
            ["Sales", "Engineering", "Sales", "Support", "Engineering", "Sales", "Support"]
        )

        assert profile.type is InferredType.CATEGORICAL
        assert profile.scale == []

    def test_a_scale_with_one_foreign_option_is_not_ordinal(self) -> None:
        """One unexpected answer means the column is not that scale.

        Guessing where "Not applicable" belongs between "Disagree" and
        "Agree" would invent an order the data never had.
        """
        profile = profile_of(
            ["Agree", "Disagree", "Neutral", "Not applicable", "Agree", "Disagree"]
        )

        assert profile.type is InferredType.CATEGORICAL

    def test_mostly_unique_sentences_are_free_text(self) -> None:
        profile = profile_of(
            [
                "The onboarding could be faster",
                "I would like more training",
                "Nothing to add really",
                "The tooling is slow sometimes",
                "More flexible hours please",
            ]
        )

        assert profile.type is InferredType.FREE_TEXT

    def test_an_all_missing_column_is_free_text(self) -> None:
        """With nothing to go on, pick the type that is excluded from tests."""
        profile = profile_of(["", "N/A", None, "-"])

        assert profile.type is InferredType.FREE_TEXT


class TestCounts:
    def test_missing_answers_are_counted_not_dropped(self) -> None:
        """Participation rate is a finding in itself, so absences are data."""
        profile = profile_of(["Yes", "No", "N/A", "Yes", "", "No"])

        assert profile.missing_count == 2
        assert profile.distinct_values == 2

    def test_distinct_count_ignores_spacing_differences(self) -> None:
        profile = profile_of(["Yes", "yes ", " Yes", "No"])

        # "Yes", "yes " and " Yes" normalize to the same two-character answer,
        # so the column has two distinct answers, not four.
        assert profile.distinct_values == 2

    def test_position_and_text_come_from_the_column_order(self) -> None:
        profiles = profile_frame(
            pd.DataFrame({"How old are you?": [30, 40], "Where?": ["Lima", "Quito"]})
        )

        assert [p.position for p in profiles] == [0, 1]
        assert profiles[0].text == "How old are you?"
        assert profiles[1].text == "Where?"
