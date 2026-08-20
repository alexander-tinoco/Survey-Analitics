"""Tests for the survey and dataset pages."""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.surveys.models import Dataset, Survey
from apps.surveys.services.ingestion import ingest
from apps.surveys.services.parsing import parse_upload

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client: Client, owner: object) -> Client:
    client.force_login(owner)
    return client


class TestAccessControl:
    @pytest.mark.parametrize("route", ["surveys:list", "surveys:create"])
    def test_pages_require_login(self, client: Client, route: str) -> None:
        response = client.get(reverse(route))

        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_a_survey_is_invisible_to_other_users(self, client: Client, survey: Survey) -> None:
        """Ownership is filtered in the queryset, so a wrong id is a 404 and
        never a peek at someone else's data.
        """
        intruder = User.objects.create_user(email="other@example.com", password="correct-horse")
        client.force_login(intruder)

        response = client.get(reverse("surveys:detail", args=[survey.pk]))

        assert response.status_code == 404

    def test_the_dataset_url_leads_to_its_record(
        self, logged_in: Client, survey: Survey, csv_file: bytes
    ) -> None:
        """A dataset's own page is its analysis record; the old URL only
        keeps existing links alive.
        """
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))

        response = logged_in.get(reverse("surveys:dataset_detail", args=[dataset.pk]))

        assert response.status_code == 302
        assert response.url == reverse("analytics:record", args=[dataset.pk])

    def test_uploading_to_another_users_survey_is_refused(
        self, client: Client, survey: Survey, csv_file: bytes
    ) -> None:
        intruder = User.objects.create_user(email="other@example.com", password="correct-horse")
        client.force_login(intruder)

        response = client.post(
            reverse("surveys:upload", args=[survey.pk]),
            {"file": SimpleUploadedFile("survey.csv", csv_file, content_type="text/csv")},
        )

        assert response.status_code == 404
        assert Dataset.objects.count() == 0


class TestSurveyList:
    def test_empty_state_shows_a_cat(self, logged_in: Client) -> None:
        """Empty states are where the illustrations belong."""
        content = logged_in.get(reverse("surveys:list")).content.decode()

        assert "Nothing recorded yet" in content
        assert "img/cat400.png" in content

    def test_listing_shows_the_users_surveys(self, logged_in: Client, survey: Survey) -> None:
        response = logged_in.get(reverse("surveys:list"))

        assert survey.name in response.content.decode()

    def test_starting_a_record_creates_survey_and_dataset_together(
        self, logged_in: Client, csv_file: bytes
    ) -> None:
        """One step, not two: an empty survey has no meaning, so the old split
        cost a screen and taught a container concept before it paid off.
        """
        response = logged_in.post(
            reverse("surveys:create"),
            {
                "name": "Client survey",
                "description": "",
                "file": SimpleUploadedFile("survey.csv", csv_file, content_type="text/csv"),
            },
        )

        created = Survey.objects.get(name="Client survey")
        # Owner comes from the session, never from submitted data.
        assert created.owner.email == "owner@example.com"
        assert created.datasets.count() == 1
        assert response.url == reverse("analytics:record", args=[created.datasets.first().pk])

    def test_a_rejected_file_leaves_no_empty_survey_behind(self, logged_in: Client) -> None:
        """Parsing runs before the survey is created, so a bad upload cannot
        strand a record the user then has to find and delete.
        """
        response = logged_in.post(
            reverse("surveys:create"),
            {
                "name": "Doomed survey",
                "description": "",
                "file": SimpleUploadedFile("survey.csv", b"Age,Age\n34,35\n"),
            },
        )

        assert response.status_code == 200
        assert "appears more than once" in response.content.decode()
        assert not Survey.objects.filter(name="Doomed survey").exists()


class TestUpload:
    def test_uploading_ingests_the_file(
        self, logged_in: Client, survey: Survey, csv_file: bytes
    ) -> None:
        response = logged_in.post(
            reverse("surveys:upload", args=[survey.pk]),
            {"file": SimpleUploadedFile("survey.csv", csv_file, content_type="text/csv")},
            follow=True,
        )

        assert response.status_code == 200
        dataset = Dataset.objects.get()
        assert dataset.respondent_count == 5
        assert dataset.question_count == 4

    def test_a_malformed_file_reports_the_reason(self, logged_in: Client, survey: Survey) -> None:
        """The parser's message reaches the uploader, who can act on it."""
        response = logged_in.post(
            reverse("surveys:upload", args=[survey.pk]),
            {"file": SimpleUploadedFile("survey.csv", b"Age,Age\n34,35\n")},
        )

        assert response.status_code == 200
        assert "appears more than once" in response.content.decode()
        assert Dataset.objects.count() == 0

    def test_a_wrong_file_type_is_refused_before_parsing(
        self, logged_in: Client, survey: Survey
    ) -> None:
        response = logged_in.post(
            reverse("surveys:upload", args=[survey.pk]),
            {"file": SimpleUploadedFile("notes.pdf", b"%PDF-1.4")},
        )

        assert response.status_code == 200
        assert "Upload a .csv" in response.content.decode()
        assert Dataset.objects.count() == 0

    def test_an_oversized_file_is_refused(self, logged_in: Client, survey: Survey) -> None:
        """Rejected on size before it is read into memory."""
        from apps.surveys.forms import MAX_UPLOAD_BYTES

        oversized = SimpleUploadedFile("big.csv", b"x" * (MAX_UPLOAD_BYTES + 1))

        response = logged_in.post(reverse("surveys:upload", args=[survey.pk]), {"file": oversized})

        assert "larger than" in response.content.decode()
        assert Dataset.objects.count() == 0


class TestVersionHistory:
    def test_the_survey_lists_its_uploads(
        self, logged_in: Client, survey: Survey, csv_file: bytes
    ) -> None:
        dataset = ingest(survey, parse_upload(csv_file, "survey.csv"))

        content = logged_in.get(reverse("surveys:detail", args=[survey.pk])).content.decode()

        assert "survey.csv" in content
        assert f"Version {dataset.version}" in content

    def test_every_upload_is_listed(
        self, logged_in: Client, survey: Survey, csv_file: bytes
    ) -> None:
        ingest(survey, parse_upload(csv_file, "first.csv"))
        ingest(survey, parse_upload(csv_file, "second.csv"))

        content = logged_in.get(reverse("surveys:detail", args=[survey.pk])).content.decode()

        assert "first.csv" in content
        assert "second.csv" in content
        assert "Version 1" in content
        assert "Version 2" in content
