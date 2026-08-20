"""Tests for the insights API endpoint."""

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.analytics.services import patterns, relational
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
def linked_dataset(owner: object) -> object:
    """A dataset with a relationship strong enough to be worth narrating.

    Of the 60 who answered "Unsatisfied", 48 also reported "Low" support
    (80.0%), against 54 of 120 overall (45.0%).
    """
    survey = Survey.objects.create(owner=owner, name="Support survey")

    rows = "Satisfaction,Support\n"
    rows += "Unsatisfied,Low\n" * 48
    rows += "Unsatisfied,High\n" * 12
    rows += "Satisfied,Low\n" * 6
    rows += "Satisfied,High\n" * 54

    return ingest(survey, parse_upload(rows.encode(), "support.csv"))


@pytest.fixture
def logged_in(client: Client, owner: object) -> Client:
    client.force_login(owner)
    return client


def prepare(dataset: object) -> None:
    """Run both background layers so the page has everything."""
    relational.compute_and_cache(dataset.pk)
    patterns.compute_and_cache(dataset.pk)


class TestAccessControl:
    def test_the_page_requires_login(self, client: Client, linked_dataset: object) -> None:
        response = client.get(reverse("analytics:insights", args=[linked_dataset.pk]))

        assert response.status_code == 302

    def test_another_users_dataset_is_not_readable(
        self, client: Client, linked_dataset: object
    ) -> None:
        intruder = User.objects.create_user(email="other@example.com", password="correct-horse")
        client.force_login(intruder)

        response = client.get(reverse("analytics_api:insights", args=[linked_dataset.pk]))

        assert response.status_code == 404

    def test_the_api_requires_authentication(self, client: Client, linked_dataset: object) -> None:
        response = client.get(reverse("analytics_api:insights", args=[linked_dataset.pk]))

        assert response.status_code == 401
