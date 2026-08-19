"""Tests for the relational dashboard and its polling endpoint."""

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.analytics.services import relational
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

        response = client.get(reverse("analytics:relational", args=[dataset.pk]))

        assert response.status_code == 404

    def test_the_api_requires_authentication(self, client: Client, dataset: object) -> None:
        response = client.get(reverse("analytics_api:relational", args=[dataset.pk]))

        assert response.status_code == 401


class TestProcessingState:
    def test_a_first_visit_shows_the_working_state_and_queues_the_job(
        self, logged_in: Client, dataset: object
    ) -> None:
        """A first visit starts the work instead of showing an unexplained
        empty page.
        """
        from unittest.mock import patch

        with patch("apps.analytics.tasks.compute_relational_analysis.delay") as queued:
            content = logged_in.get(
                reverse("analytics:relational", args=[dataset.pk])
            ).content.decode()

        queued.assert_called_once_with(dataset.pk)
        assert "Crunching the numbers" in content
        assert "data-poll-url" in content

    def test_the_working_state_is_the_one_place_a_cat_appears(
        self, logged_in: Client, dataset: object
    ) -> None:
        """Waiting is an empty state, which is where the illustrations live."""
        from unittest.mock import patch

        with patch("apps.analytics.tasks.compute_relational_analysis.delay"):
            content = logged_in.get(
                reverse("analytics:relational", args=[dataset.pk])
            ).content.decode()

        assert "img/cat401.png" in content

    def test_the_api_answers_202_while_the_job_runs(
        self, logged_in: Client, dataset: object
    ) -> None:
        """202 tells a client to poll; 200 with an empty list would read as
        "analysis finished and found nothing".
        """
        from unittest.mock import patch

        with patch("apps.analytics.tasks.compute_relational_analysis.delay"):
            response = logged_in.get(reverse("analytics_api:relational", args=[dataset.pk]))

        assert response.status_code == 202
        assert response.json()["status"] == "running"


class TestResults:
    def test_finished_analysis_renders_its_tables(self, logged_in: Client, dataset: object) -> None:
        relational.compute_and_cache(dataset.pk)

        content = logged_in.get(reverse("analytics:relational", args=[dataset.pk])).content.decode()

        assert "Department" in content
        assert "Cram" in content
        assert "<table" in content

    def test_results_carry_no_cats(self, logged_in: Client, dataset: object) -> None:
        relational.compute_and_cache(dataset.pk)

        content = logged_in.get(reverse("analytics:relational", args=[dataset.pk])).content.decode()

        assert "cat-panel__art" not in content

    def test_the_api_answers_200_once_results_exist(
        self, logged_in: Client, dataset: object
    ) -> None:
        relational.compute_and_cache(dataset.pk)

        response = logged_in.get(reverse("analytics_api:relational", args=[dataset.pk]))

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert len(body["associations"]) >= 1

    def test_each_association_reports_its_effect_size_and_reliability(
        self, logged_in: Client, dataset: object
    ) -> None:
        """Significance without effect size is how a trivial link gets
        reported as a finding.
        """
        relational.compute_and_cache(dataset.pk)

        association = logged_in.get(reverse("analytics_api:relational", args=[dataset.pk])).json()[
            "associations"
        ][0]

        assert "cramers_v" in association
        assert "strength" in association
        assert "is_reliable" in association
        assert "adjusted_p_value" in association

    def test_a_dataset_with_nothing_to_cross_tabulate_says_so(
        self, logged_in: Client, survey: object
    ) -> None:
        """Numeric and free-text answers have no categories to compare."""
        content = (
            b"Age,Comments\n"
            b"34,A long comment about the onboarding\n"
            b"29,Another different remark here\n"
            b"45,Something else entirely written\n"
        )
        numeric_only = ingest(survey, parse_upload(content, "numbers.csv"))
        relational.compute_and_cache(numeric_only.pk)

        page = logged_in.get(
            reverse("analytics:relational", args=[numeric_only.pk])
        ).content.decode()

        assert "Nothing to cross-tabulate" in page

    def test_an_unreliable_result_is_flagged_in_the_page(
        self, logged_in: Client, dataset: object
    ) -> None:
        """Five respondents cannot support a chi-square, and the page must
        say so rather than presenting a p-value as if it meant something.
        """
        relational.compute_and_cache(dataset.pk)

        content = logged_in.get(reverse("analytics:relational", args=[dataset.pk])).content.decode()

        report = relational.get_report(dataset)
        if any(not a.is_reliable for a in report.associations):
            assert "not trustworthy" in content or "Too few respondents" in content
