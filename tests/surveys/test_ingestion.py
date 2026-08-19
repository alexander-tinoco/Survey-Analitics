"""Tests for turning a parsed file into database rows."""

import pytest

from apps.surveys.models import Dataset, Question, QuestionType, Response
from apps.surveys.services.ingestion import ingest
from apps.surveys.services.parsing import parse_upload

pytestmark = pytest.mark.django_db


class TestIngestion:
    def test_creates_one_response_per_respondent_and_question(
        self, survey: object, csv_file: bytes
    ) -> None:
        """Long format: the row count is respondents times questions."""
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))

        assert dataset.respondent_count == 5
        assert dataset.question_count == 4
        assert Response.objects.filter(dataset=dataset).count() == 20

    def test_questions_keep_the_column_order(self, survey: object, csv_file: bytes) -> None:
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))

        texts = list(dataset.questions.values_list("text", flat=True))
        assert texts == ["Age", "Department", "Satisfaction", "Comments"]

    def test_question_types_are_inferred_and_stored(self, survey: object, csv_file: bytes) -> None:
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))

        types = dict(dataset.questions.values_list("text", "type"))
        assert types["Age"] == QuestionType.NUMERIC
        assert types["Department"] == QuestionType.CATEGORICAL
        assert types["Satisfaction"] == QuestionType.ORDINAL
        assert types["Comments"] == QuestionType.FREE_TEXT

    def test_raw_values_are_preserved(self, survey: object, csv_file: bytes) -> None:
        """A parsing bug must be fixable without a re-upload."""
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))
        question = dataset.questions.get(text="Department")

        raw = set(question.responses.values_list("raw_value", flat=True))
        assert raw == {"Sales", "Engineering", "Support"}

    def test_ordinal_answers_get_their_rank_as_a_number(
        self, survey: object, csv_file: bytes
    ) -> None:
        """Text alone sorts alphabetically, which would rank Agree above
        Neutral for the wrong reason. The scale position makes order real.
        """
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))
        question = dataset.questions.get(text="Satisfaction")

        ranks = {
            response.normalized_value: response.numeric_value
            for response in question.responses.all()
        }
        assert ranks["Disagree"] < ranks["Neutral"] < ranks["Agree"] < ranks["Strongly agree"]

    def test_numeric_answers_are_stored_as_numbers(self, survey: object, csv_file: bytes) -> None:
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))
        question = dataset.questions.get(text="Age")

        values = sorted(question.responses.values_list("numeric_value", flat=True))
        assert values == [29.0, 34.0, 38.0, 45.0, 52.0]

    def test_missing_answers_are_flagged_not_dropped(self, survey: object, csv_file: bytes) -> None:
        """The blank comment is a row with is_missing, not an absent row.

        Dropping it would make the response count disagree with the
        respondent count, and participation rate uncomputable.
        """
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))
        question = dataset.questions.get(text="Comments")

        assert question.responses.count() == 5
        assert question.responses.filter(is_missing=True).count() == 1
        assert question.missing_count == 1
        assert question.answered_count == 4

    def test_every_respondent_gets_a_stable_key(self, survey: object, csv_file: bytes) -> None:
        """Answers must be reassemblable per person for clustering."""
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))

        keys = set(dataset.responses.values_list("respondent_key", flat=True))
        assert keys == {"r1", "r2", "r3", "r4", "r5"}

        first_person = dataset.responses.filter(respondent_key="r1")
        assert first_person.count() == 4


class TestVersioning:
    def test_first_upload_is_version_one(self, survey: object, csv_file: bytes) -> None:
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))

        assert dataset.version == 1

    def test_re_uploading_creates_a_new_version(self, survey: object, csv_file: bytes) -> None:
        """Nothing is overwritten, which is what makes cache keys safe."""
        first = ingest(survey, parse_upload(csv_file, "first.csv"))
        second = ingest(survey, parse_upload(csv_file, "second.csv"))

        assert first.version == 1
        assert second.version == 2
        assert Dataset.objects.filter(survey=survey).count() == 2

    def test_earlier_versions_keep_their_own_rows(self, survey: object, csv_file: bytes) -> None:
        first = ingest(survey, parse_upload(csv_file, "first.csv"))
        shorter = b"Age,Department\n34,Sales\n"

        ingest(survey, parse_upload(shorter, "second.csv"))

        assert first.questions.count() == 4
        assert first.responses.count() == 20

    def test_latest_dataset_is_the_newest_version(self, survey: object, csv_file: bytes) -> None:
        ingest(survey, parse_upload(csv_file, "first.csv"))
        second = ingest(survey, parse_upload(csv_file, "second.csv"))

        assert survey.latest_dataset == second


class TestIntegrity:
    def test_a_respondent_cannot_answer_one_question_twice(
        self, survey: object, csv_file: bytes
    ) -> None:
        """The constraint is real, not just a convention in the writer."""
        from django.db import IntegrityError

        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))
        question = dataset.questions.first()

        with pytest.raises(IntegrityError):
            Response.objects.create(
                dataset=dataset, question=question, respondent_key="r1", raw_value="duplicate"
            )

    def test_deleting_a_dataset_removes_its_rows(self, survey: object, csv_file: bytes) -> None:
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))

        dataset.delete()

        assert Response.objects.count() == 0
        assert Question.objects.count() == 0
