"""Tests for the ORM-to-DataFrame boundary.

These need a database, unlike the engine tests. That split is the point of
ADR 0001: the slow tests cover translation, the fast ones cover statistics.
"""

import pytest

from apps.analytics.services.descriptive import describe
from apps.analytics.services.frames import load
from apps.surveys.services.ingestion import ingest
from apps.surveys.services.parsing import parse_upload

pytestmark = pytest.mark.django_db


@pytest.fixture
def dataset(survey: object, csv_file: bytes) -> object:
    return ingest(survey, parse_upload(csv_file, "survey.csv"))


class TestFrameLoading:
    def test_long_rows_become_one_row_per_respondent(self, dataset: object) -> None:
        """20 stored answers become a 5x4 frame."""
        loaded = load(dataset)

        assert dataset.responses.count() == 20
        assert loaded.frame.shape == (5, 4)

    def test_columns_keep_the_questionnaire_order(self, dataset: object) -> None:
        """pivot sorts columns alphabetically, which would scramble a survey.

        Alphabetically these would come out Age, Comments, Department,
        Satisfaction — an order nobody was asked the questions in.
        """
        loaded = load(dataset)

        assert list(loaded.frame.columns) == ["Age", "Department", "Satisfaction", "Comments"]

    def test_missing_answers_become_null_not_empty_string(self, dataset: object) -> None:
        """An empty string would be counted as an answer everyone shared."""
        loaded = load(dataset)

        assert loaded.frame["Comments"].isna().sum() == 1

    def test_question_types_come_from_ingestion(self, dataset: object) -> None:
        """The engine must not re-infer types: storage and analysis have to
        agree on what a question is.
        """
        loaded = load(dataset)

        assert loaded.question_types["Age"] == "numeric"
        assert loaded.question_types["Satisfaction"] == "ordinal"

    def test_ordinal_scale_order_is_recovered_from_the_stored_ranks(self, dataset: object) -> None:
        """No separate scale field: the rank written at ingestion already
        encodes the order, and deriving it removes a second source of truth
        that could drift from the data.
        """
        loaded = load(dataset)

        assert loaded.scales["Satisfaction"] == [
            "disagree",
            "neutral",
            "agree",
            "strongly agree",
        ]

    def test_a_dataset_without_ordinal_questions_needs_no_scales(self, survey: object) -> None:
        """Scale recovery is skipped entirely rather than scanning for
        nothing — most datasets have no ordinal column at all.
        """
        content = b"Age,City\n34,Lima\n29,Quito\n45,Bogota\n"

        loaded = load(ingest(survey, parse_upload(content, "plain.csv")))

        assert loaded.scales == {}
        assert loaded.question_types["Age"] == "numeric"

    def test_a_dataset_with_no_responses_yields_an_empty_frame(self, survey: object) -> None:
        from apps.surveys.models import Dataset

        empty = Dataset.objects.create(survey=survey, version=99, source_filename="x.csv")

        loaded = load(empty)

        assert loaded.frame.empty
        assert loaded.scales == {}


class TestDescribeService:
    def test_summary_reflects_the_stored_dataset(self, dataset: object) -> None:
        summary = describe(dataset)

        assert summary.respondents == 5
        assert summary.questions == 4

    def test_ordinal_distribution_follows_the_recovered_scale(self, dataset: object) -> None:
        """End to end: ranks stored at ingestion drive the chart order."""
        summary = describe(dataset)
        satisfaction = next(d for d in summary.distributions if d.text == "Satisfaction")

        assert [c.value for c in satisfaction.counts] == [
            "Disagree",
            "Neutral",
            "Agree",
            "Strongly agree",
        ]

    def test_numeric_question_gets_a_summary(self, dataset: object) -> None:
        """Ages 34, 29, 45, 38, 52.

        mean = 198/5 = 39.6, median = 38, min = 29, max = 52.
        """
        summary = describe(dataset)
        age = next(d for d in summary.distributions if d.text == "Age")

        assert age.numeric.mean == 39.6
        assert age.numeric.median == 38.0
        assert age.numeric.minimum == 29.0
        assert age.numeric.maximum == 52.0

    def test_missing_answers_lower_the_response_rate(self, dataset: object) -> None:
        """One of five comments is blank: 4/5 = 80.0%."""
        summary = describe(dataset)
        comments = next(d for d in summary.distributions if d.text == "Comments")

        assert comments.response_rate == 80.0
        assert summary.lowest_response_rate.text == "Comments"
