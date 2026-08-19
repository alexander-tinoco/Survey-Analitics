"""Coverage of the paths that only run when something is unusual.

These branches exist for real files: an export with 40 columns of prose, a
scale stored as digits, a truncated download. They are the least exercised
code in the ingestion path and the most likely to be wrong.
"""

import pandas as pd
import pytest

from apps.surveys.models import QuestionType
from apps.surveys.services.inference import (
    ALWAYS_CATEGORICAL_DISTINCT,
    MAX_CATEGORICAL_DISTINCT,
    MIN_ROWS_FOR_UNIQUE_RATIO,
    InferredType,
    profile_frame,
)
from apps.surveys.services.ingestion import ingest
from apps.surveys.services.parsing import MAX_ROWS, ParseError, parse_upload


def profile_of(values: list[object]):
    return profile_frame(pd.DataFrame({"Q1": values}))[0]


class TestCategoricalBoundaries:
    def test_too_many_options_is_free_text(self) -> None:
        """Past the cap a column is prose no matter how short the answers."""
        values = [f"opt{i}" for i in range(MAX_CATEGORICAL_DISTINCT + 1)] * 2

        assert profile_of(values).type is InferredType.FREE_TEXT

    def test_a_repetitive_column_above_the_always_threshold_is_categorical(self) -> None:
        """Between the two thresholds, repetition is what decides.

        Enough rows for the ratio to mean something, and each option used
        several times: a fixed option list, not prose.
        """
        options = [f"team{i}" for i in range(ALWAYS_CATEGORICAL_DISTINCT + 2)]
        values = options * 5

        assert len(values) >= MIN_ROWS_FOR_UNIQUE_RATIO
        assert profile_of(values).type is InferredType.CATEGORICAL

    def test_a_barely_repeated_column_with_many_rows_is_free_text(self) -> None:
        """Same option count, but almost every answer is unique."""
        options = [f"answer {i}" for i in range(MAX_CATEGORICAL_DISTINCT)]
        values = [*options, *options[:2]]

        profile = profile_of(values)

        assert profile.distinct_values == MAX_CATEGORICAL_DISTINCT
        assert profile.type is InferredType.FREE_TEXT

    def test_a_column_of_only_blanks_yields_no_scale(self) -> None:
        assert profile_of(["", "  ", None]).scale == []


@pytest.mark.django_db
class TestNumericConversion:
    def test_a_digit_scale_keeps_its_own_values_as_ranks(self, survey: object) -> None:
        """A 1-5 scale stored as digits ranks by its value, not its position.

        Position would be right here by coincidence; it is wrong the moment a
        rung goes unused, which is why the digits are parsed directly.
        """
        content = b"Rating\n1\n3\n5\n1\n5\n"

        dataset = ingest(survey, parse_upload(content, "ratings.csv"))
        question = dataset.questions.get(text="Rating")

        assert question.type == QuestionType.ORDINAL
        values = sorted(question.responses.values_list("numeric_value", flat=True))
        assert values == [1.0, 1.0, 3.0, 5.0, 5.0]

    def test_a_non_numeric_answer_in_a_numeric_column_stores_no_number(
        self, survey: object
    ) -> None:
        """The row is kept with its raw text rather than silently dropped."""
        content = b"Age\n34\n29\n45\n38\n52\n61\n27\nunknown\n"

        dataset = ingest(survey, parse_upload(content, "ages.csv"))
        question = dataset.questions.get(text="Age")

        assert question.responses.filter(numeric_value__isnull=True).count() == 1
        odd_one = question.responses.get(numeric_value__isnull=True)
        assert odd_one.raw_value == "unknown"
        assert odd_one.is_missing is False


class TestParserLimits:
    def test_a_file_with_only_delimiters_is_rejected(self) -> None:
        with pytest.raises(ParseError):
            parse_upload(b",,,\n,,,\n", "survey.csv")

    def test_bytes_that_are_not_utf_8_still_read(self) -> None:
        """latin-1 maps every byte, so an odd encoding never loses a file.

        The row survives with its text mangled rather than being refused;
        anything that is genuinely not survey data is caught by the
        structural checks instead.
        """
        content = b"Age\n\xff\xfe\x00\x00invalid\x81\x8d\n"

        parsed = parse_upload(content, "survey.csv")

        assert list(parsed.frame.columns) == ["Age"]
        assert parsed.respondent_count == 1

    def test_a_single_column_file_keeps_its_header_intact(self) -> None:
        """Regression: a sniffed delimiter once split "Rating" on the t."""
        parsed = parse_upload(b"Rating\n1\n3\n5\n", "survey.csv")

        assert list(parsed.frame.columns) == ["Rating"]
        assert parsed.respondent_count == 3

    def test_too_many_rows_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The cap is enforced; the limit is patched down to keep this fast."""
        monkeypatch.setattr("apps.surveys.services.parsing.MAX_ROWS", 3)
        content = b"Age\n1\n2\n3\n4\n5\n"

        with pytest.raises(ParseError, match="more than"):
            parse_upload(content, "survey.csv")

        assert MAX_ROWS == 100_000


@pytest.mark.django_db
class TestModelRepresentations:
    def test_models_describe_themselves_readably(self, survey: object, csv_file: bytes) -> None:
        """__str__ is what the admin and error messages show."""
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))
        question = dataset.questions.get(text="Department")
        response = question.responses.first()

        assert str(survey) == "Employee survey"
        assert str(dataset) == "Employee survey v1"
        assert str(question) == "Department"
        assert response.respondent_key in str(response)
