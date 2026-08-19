"""Tests for pagination, deletion and retention of the uploaded file."""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.surveys.models import Dataset, Question, Response, Survey
from apps.surveys.services.ingestion import ingest
from apps.surveys.services.parsing import parse_upload

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client: Client, owner: object) -> Client:
    client.force_login(owner)
    return client


class TestPagination:
    def test_a_long_list_is_split_into_pages(self, logged_in: Client, owner: object) -> None:
        """Without a page size, an account with hundreds of surveys builds
        every one of them into a single response.
        """
        for index in range(25):
            Survey.objects.create(owner=owner, name=f"Survey {index:02d}")

        first = logged_in.get(reverse("surveys:list"))

        assert first.context["is_paginated"] is True
        assert len(first.context["surveys"]) == 20
        assert first.context["page_obj"].paginator.count == 25

    def test_the_second_page_holds_the_remainder(self, logged_in: Client, owner: object) -> None:
        for index in range(25):
            Survey.objects.create(owner=owner, name=f"Survey {index:02d}")

        second = logged_in.get(reverse("surveys:list"), {"page": 2})

        assert len(second.context["surveys"]) == 5

    def test_a_short_list_shows_no_pagination_control(
        self, logged_in: Client, survey: Survey
    ) -> None:
        response = logged_in.get(reverse("surveys:list"))

        assert response.context["is_paginated"] is False
        assert "Pagination" not in response.content.decode()

    def test_listing_surveys_does_not_query_per_row(
        self, logged_in: Client, owner: object, django_assert_max_num_queries: object
    ) -> None:
        """The list shows each survey's newest dataset. Without prefetching,
        that is one extra query per row.
        """
        for index in range(15):
            survey = Survey.objects.create(owner=owner, name=f"Survey {index:02d}")
            Dataset.objects.create(survey=survey, version=1, source_filename="x.csv")

        with django_assert_max_num_queries(6):
            logged_in.get(reverse("surveys:list"))


class TestFileRetention:
    def test_the_uploaded_file_is_kept(
        self, logged_in: Client, survey: Survey, csv_file: bytes
    ) -> None:
        """raw_value protects a single cell; only the original file allows
        re-deriving everything after a parser fix.
        """
        logged_in.post(
            reverse("surveys:upload", args=[survey.pk]),
            {"file": SimpleUploadedFile("survey.csv", csv_file, content_type="text/csv")},
        )

        dataset = Dataset.objects.get()
        assert dataset.source_file
        assert dataset.source_file.read() == csv_file

    def test_the_owner_can_download_it_back(
        self, logged_in: Client, survey: Survey, csv_file: bytes
    ) -> None:
        logged_in.post(
            reverse("surveys:upload", args=[survey.pk]),
            {"file": SimpleUploadedFile("survey.csv", csv_file, content_type="text/csv")},
        )
        dataset = Dataset.objects.get()

        response = logged_in.get(reverse("surveys:dataset_file", args=[dataset.pk]))

        assert response.status_code == 200
        assert b"".join(response.streaming_content) == csv_file
        assert "attachment" in response["Content-Disposition"]

    def test_another_user_cannot_download_it(
        self, client: Client, survey: Survey, csv_file: bytes
    ) -> None:
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))
        intruder = User.objects.create_user(email="other@example.com", password="correct-horse")
        client.force_login(intruder)

        response = client.get(reverse("surveys:dataset_file", args=[dataset.pk]))

        assert response.status_code == 404

    def test_a_dataset_without_a_stored_file_says_so(
        self, logged_in: Client, survey: Survey
    ) -> None:
        """Datasets ingested before retention existed have nothing to serve,
        and a 404 beats a 500 from a missing path.
        """
        legacy = Dataset.objects.create(survey=survey, version=1, source_filename="old.csv")

        response = logged_in.get(reverse("surveys:dataset_file", args=[legacy.pk]))

        assert response.status_code == 404


class TestDeletion:
    def test_deleting_a_survey_removes_everything_under_it(
        self, logged_in: Client, survey: Survey, csv_file: bytes
    ) -> None:
        ingest(survey, parse_upload(csv_file, "survey.csv"))

        logged_in.post(reverse("surveys:delete", args=[survey.pk]))

        assert Survey.objects.count() == 0
        assert Dataset.objects.count() == 0
        assert Question.objects.count() == 0
        assert Response.objects.count() == 0

    def test_deleting_a_survey_removes_its_stored_files(
        self, logged_in: Client, survey: Survey, csv_file: bytes
    ) -> None:
        """A bulk cascade drops the rows and leaves the uploads orphaned on
        disk, so datasets are deleted one by one.
        """
        logged_in.post(
            reverse("surveys:upload", args=[survey.pk]),
            {"file": SimpleUploadedFile("survey.csv", csv_file, content_type="text/csv")},
        )
        stored = Dataset.objects.get().source_file
        assert stored.storage.exists(stored.name)

        logged_in.post(reverse("surveys:delete", args=[survey.pk]))

        assert not stored.storage.exists(stored.name)

    def test_deleting_one_version_leaves_the_others(
        self, logged_in: Client, survey: Survey, csv_file: bytes
    ) -> None:
        first = ingest(survey, parse_upload(csv_file, "first.csv"))
        second = ingest(survey, parse_upload(csv_file, "second.csv"))

        logged_in.post(reverse("surveys:dataset_delete", args=[second.pk]))

        assert Dataset.objects.filter(pk=first.pk).exists()
        assert not Dataset.objects.filter(pk=second.pk).exists()
        assert Survey.objects.filter(pk=survey.pk).exists()

    def test_deletion_requires_a_post(self, logged_in: Client, survey: Survey) -> None:
        """A GET shows the confirmation page and destroys nothing: a link
        that deletes on visit can be fired by a prefetch.
        """
        response = logged_in.get(reverse("surveys:delete", args=[survey.pk]))

        assert response.status_code == 200
        assert Survey.objects.filter(pk=survey.pk).exists()

    def test_the_confirmation_states_what_will_be_lost(
        self, logged_in: Client, survey: Survey, csv_file: bytes
    ) -> None:
        """A generic "are you sure" hides that this is tens of thousands of
        rows and cannot be undone.
        """
        ingest(survey, parse_upload(csv_file, "survey.csv"))

        content = logged_in.get(reverse("surveys:delete", args=[survey.pk])).content.decode()

        assert "cannot be undone" in content
        assert survey.name in content

    def test_another_user_cannot_delete_a_survey(self, client: Client, survey: Survey) -> None:
        intruder = User.objects.create_user(email="other@example.com", password="correct-horse")
        client.force_login(intruder)

        response = client.post(reverse("surveys:delete", args=[survey.pk]))

        assert response.status_code == 404
        assert Survey.objects.filter(pk=survey.pk).exists()

    def test_another_user_cannot_delete_a_dataset(
        self, client: Client, survey: Survey, csv_file: bytes
    ) -> None:
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))
        intruder = User.objects.create_user(email="other@example.com", password="correct-horse")
        client.force_login(intruder)

        response = client.post(reverse("surveys:dataset_delete", args=[dataset.pk]))

        assert response.status_code == 404
        assert Dataset.objects.filter(pk=dataset.pk).exists()

    def test_deletion_requires_login(self, client: Client, survey: Survey) -> None:
        response = client.post(reverse("surveys:delete", args=[survey.pk]))

        assert response.status_code == 302
        assert Survey.objects.filter(pk=survey.pk).exists()
