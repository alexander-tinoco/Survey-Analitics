"""Tests for exporting findings."""

import csv
import io

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.analytics.services import insights, patterns, relational
from apps.surveys.models import Survey
from apps.surveys.services.ingestion import ingest
from apps.surveys.services.parsing import parse_upload

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache() -> None:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def analyzed(owner: object) -> object:
    """A dataset with a finding worth exporting, fully analyzed."""
    survey = Survey.objects.create(owner=owner, name="Support survey")
    rows = "Satisfaction,Support\n"
    rows += "Unsatisfied,Low\n" * 48
    rows += "Unsatisfied,High\n" * 12
    rows += "Satisfied,Low\n" * 6
    rows += "Satisfied,High\n" * 54
    dataset = ingest(survey, parse_upload(rows.encode(), "support.csv"))

    relational.compute_and_cache(dataset.pk)
    patterns.compute_and_cache(dataset.pk)
    return dataset


@pytest.fixture
def logged_in(client: Client, owner: object) -> Client:
    client.force_login(owner)
    return client


class TestCsvExport:
    def test_the_export_downloads_as_a_file(self, logged_in: Client, analyzed: object) -> None:
        response = logged_in.get(reverse("analytics:insights_export", args=[analyzed.pk, "csv"]))

        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
        assert "attachment" in response["Content-Disposition"]

    def test_the_filename_names_the_survey_and_version(
        self, logged_in: Client, analyzed: object
    ) -> None:
        """Two exports of the same survey are otherwise indistinguishable in
        a downloads folder, which is exactly where they end up.
        """
        response = logged_in.get(reverse("analytics:insights_export", args=[analyzed.pk, "csv"]))

        assert "support-survey-v1-findings.csv" in response["Content-Disposition"]

    def test_every_finding_becomes_a_row(self, logged_in: Client, analyzed: object) -> None:
        response = logged_in.get(reverse("analytics:insights_export", args=[analyzed.pk, "csv"]))
        rows = list(csv.DictReader(io.StringIO(response.content.decode())))

        expected = insights.build(analyzed).insights
        assert len(rows) == len(expected)
        assert rows[0]["finding"] == expected[0].text

    def test_rows_carry_the_evidence_behind_each_finding(
        self, logged_in: Client, analyzed: object
    ) -> None:
        """An exported sentence without its figures is unverifiable once it
        has left the application.
        """
        response = logged_in.get(reverse("analytics:insights_export", args=[analyzed.pk, "csv"]))
        rows = list(csv.DictReader(io.StringIO(response.content.decode())))

        assert rows[0]["evidence"]
        assert "=" in rows[0]["evidence"]
        assert rows[0]["questions"]

    def test_rows_keep_the_ranking(self, logged_in: Client, analyzed: object) -> None:
        response = logged_in.get(reverse("analytics:insights_export", args=[analyzed.pk, "csv"]))
        rows = list(csv.DictReader(io.StringIO(response.content.decode())))

        assert [int(row["rank"]) for row in rows] == list(range(1, len(rows) + 1))
        relevances = [float(row["relevance"]) for row in rows]
        assert relevances == sorted(relevances, reverse=True)


class TestJsonExport:
    def test_json_carries_the_full_report(self, logged_in: Client, analyzed: object) -> None:
        response = logged_in.get(reverse("analytics:insights_export", args=[analyzed.pk, "json"]))

        assert response.status_code == 200
        body = response.json()
        assert body["complete"] is True
        assert body["insights"]
        assert "attachment" in response["Content-Disposition"]

    def test_json_matches_what_the_page_shows(self, logged_in: Client, analyzed: object) -> None:
        """An export that disagrees with the screen is worse than none."""
        exported = logged_in.get(
            reverse("analytics:insights_export", args=[analyzed.pk, "json"])
        ).json()
        on_screen = logged_in.get(reverse("analytics_api:insights", args=[analyzed.pk])).json()

        assert exported == on_screen


class TestGuards:
    def test_exporting_before_the_analysis_finishes_is_refused(
        self, logged_in: Client, owner: object
    ) -> None:
        """A file is read later, with no sign that it was partial when
        written. Better to send the user back than to hand them half an
        answer they cannot tell is half.
        """
        from unittest.mock import patch

        survey = Survey.objects.create(owner=owner, name="Fresh survey")
        rows = "A,B\nx,y\n" * 30
        dataset = ingest(survey, parse_upload(("A,B\n" + "x,y\n" * 30).encode(), "f.csv"))

        with (
            patch("apps.analytics.tasks.compute_relational_analysis.delay"),
            patch("apps.analytics.tasks.compute_pattern_analysis.delay"),
        ):
            response = logged_in.get(reverse("analytics:insights_export", args=[dataset.pk, "csv"]))

        assert response.status_code == 302
        assert reverse("analytics:insights", args=[dataset.pk]) in response.url

    def test_export_requires_login(self, client: Client, analyzed: object) -> None:
        response = client.get(reverse("analytics:insights_export", args=[analyzed.pk, "csv"]))

        assert response.status_code == 302

    def test_another_user_cannot_export(self, client: Client, analyzed: object) -> None:
        intruder = User.objects.create_user(email="other@example.com", password="correct-horse")
        client.force_login(intruder)

        response = client.get(reverse("analytics:insights_export", args=[analyzed.pk, "csv"]))

        assert response.status_code == 404
