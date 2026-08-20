"""Tests for the relational API endpoint."""

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

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
def dataset(survey: object, csv_file: bytes) -> object:
    return ingest(survey, parse_upload(csv_file, "survey.csv"))


@pytest.fixture
def logged_in(client: Client, owner: object) -> Client:
    client.force_login(owner)
    return client


class TestAccessControl:
    def test_the_page_requires_login(self, client: Client, dataset: object) -> None:
        response = client.get(reverse("analytics:relational", args=[dataset.pk]))

        assert response.status_code == 302

    def test_another_users_dataset_is_not_analyzable(self, client: Client, dataset: object) -> None:
        intruder = User.objects.create_user(email="other@example.com", password="correct-horse")
        client.force_login(intruder)

        response = client.get(reverse("analytics_api:relational", args=[dataset.pk]))

        assert response.status_code == 404

    def test_the_api_requires_authentication(self, client: Client, dataset: object) -> None:
        response = client.get(reverse("analytics_api:relational", args=[dataset.pk]))

        assert response.status_code == 401
