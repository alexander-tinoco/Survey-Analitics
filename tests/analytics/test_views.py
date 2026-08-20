"""Tests for the descriptive API endpoint."""

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

    def test_api_and_record_report_the_same_numbers(
        self, logged_in: Client, dataset: object
    ) -> None:
        """Both read one presenter, so a chart cannot disagree with a client."""
        api_body = logged_in.get(reverse("analytics_api:descriptive", args=[dataset.pk])).json()

        page = logged_in.get(reverse("analytics:record", args=[dataset.pk]))
        embedded = json.loads(
            page.content.decode()
            .split('id="chart-data" type="application/json">')[1]
            .split("</script>")[0]
        )

        assert embedded == api_body

    def test_api_requires_authentication(self, client: Client, dataset: object) -> None:
        response = client.get(reverse("analytics_api:descriptive", args=[dataset.pk]))

        assert response.status_code == 401
