"""Tests for the descriptive dashboard and its API."""

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.surveys.services.ingestion import ingest
from apps.surveys.services.parsing import parse_upload

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def dataset(survey: object, csv_file: bytes) -> object:
    return ingest(survey, parse_upload(csv_file, "survey.csv"))


@pytest.fixture
def logged_in(client: Client, owner: object) -> Client:
    client.force_login(owner)
    return client


class TestAccessControl:
    def test_dashboard_requires_login(self, client: Client, dataset: object) -> None:
        response = client.get(reverse("analytics:dashboard", args=[dataset.pk]))

        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_another_users_dataset_is_not_analyzable(self, client: Client, dataset: object) -> None:
        """Someone else's dataset id must be a 404, not a readable analysis."""
        intruder = User.objects.create_user(email="other@example.com", password="correct-horse")
        client.force_login(intruder)

        response = client.get(reverse("analytics:dashboard", args=[dataset.pk]))

        assert response.status_code == 404


class TestDashboard:
    def test_dashboard_shows_the_dataset_totals(self, logged_in: Client, dataset: object) -> None:
        content = logged_in.get(reverse("analytics:dashboard", args=[dataset.pk])).content.decode()

        assert "Respondents" in content
        assert "Employee survey" in content

    def test_every_question_gets_a_section(self, logged_in: Client, dataset: object) -> None:
        content = logged_in.get(reverse("analytics:dashboard", args=[dataset.pk])).content.decode()

        for question in ["Age", "Department", "Satisfaction", "Comments"]:
            assert question in content

    def test_each_chart_has_a_table_with_the_same_numbers(
        self, logged_in: Client, dataset: object
    ) -> None:
        """A canvas is opaque to a screen reader, so the table is required.

        Sales appears twice among five respondents: 2 and 40.0%.
        """
        content = logged_in.get(reverse("analytics:dashboard", args=[dataset.pk])).content.decode()

        assert "40.0%" in content
        assert "<table" in content

    def test_numeric_questions_show_summary_statistics(
        self, logged_in: Client, dataset: object
    ) -> None:
        """Ages 34, 29, 45, 38, 52 -> mean 39.6, median 38."""
        content = logged_in.get(reverse("analytics:dashboard", args=[dataset.pk])).content.decode()

        assert "39.6" in content
        assert "Median" in content

    def test_the_most_skipped_question_is_called_out(
        self, logged_in: Client, dataset: object
    ) -> None:
        """One blank comment of five: 80% response rate, the lowest here."""
        content = logged_in.get(reverse("analytics:dashboard", args=[dataset.pk])).content.decode()

        assert "80.0%" in content
        assert "least of any question" in content

    def test_chart_data_is_embedded_not_fetched(self, logged_in: Client, dataset: object) -> None:
        """The server already computed it to render the tables."""
        content = logged_in.get(reverse("analytics:dashboard", args=[dataset.pk])).content.decode()

        assert 'id="chart-data"' in content

    def test_the_dashboard_carries_no_cats(self, logged_in: Client, dataset: object) -> None:
        """Illustrations stay out of data views (CLAUDE.md section 5)."""
        content = logged_in.get(reverse("analytics:dashboard", args=[dataset.pk])).content.decode()

        assert "cat-panel__art" not in content


class TestDescriptiveApi:
    def test_summary_is_returned_as_json(self, logged_in: Client, dataset: object) -> None:
        response = logged_in.get(reverse("analytics_api:descriptive", args=[dataset.pk]))

        assert response.status_code == 200
        body = response.json()
        assert body["respondents"] == 5
        assert body["questions"] == 4

    def test_distributions_carry_counts_and_percentages(
        self, logged_in: Client, dataset: object
    ) -> None:
        """Sales 2 of 5 answered = 40.0%."""
        body = logged_in.get(reverse("analytics_api:descriptive", args=[dataset.pk])).json()

        department = next(d for d in body["distributions"] if d["text"] == "Department")
        sales = next(c for c in department["counts"] if c["value"] == "Sales")
        assert sales == {"value": "Sales", "count": 2, "percentage": 40.0}

    def test_ordinal_distributions_keep_their_scale_order(
        self, logged_in: Client, dataset: object
    ) -> None:
        body = logged_in.get(reverse("analytics_api:descriptive", args=[dataset.pk])).json()

        satisfaction = next(d for d in body["distributions"] if d["text"] == "Satisfaction")
        assert [c["value"] for c in satisfaction["counts"]] == [
            "Disagree",
            "Neutral",
            "Agree",
            "Strongly agree",
        ]

    def test_api_and_dashboard_report_the_same_numbers(
        self, logged_in: Client, dataset: object
    ) -> None:
        """Both read one presenter, so a chart cannot disagree with a client."""
        api_body = logged_in.get(reverse("analytics_api:descriptive", args=[dataset.pk])).json()

        page = logged_in.get(reverse("analytics:dashboard", args=[dataset.pk]))
        embedded = json.loads(
            page.content.decode()
            .split('id="chart-data" type="application/json">')[1]
            .split("</script>")[0]
        )

        assert embedded == api_body

    def test_api_requires_authentication(self, client: Client, dataset: object) -> None:
        response = client.get(reverse("analytics_api:descriptive", args=[dataset.pk]))

        assert response.status_code == 401
