"""Tests for the pattern layer's caching, job and views."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.analytics.services import patterns, relational
from apps.analytics.services.jobs import JobStatus
from apps.analytics.tasks import compute_pattern_analysis
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
def grouped_dataset(owner: object) -> object:
    """A dataset with three groups planted in it, large enough to cluster."""
    survey = Survey.objects.create(owner=owner, name="Grouped survey")

    header = "Team,Satisfaction,Tooling\n"
    rows = ""
    for team, satisfaction, tooling in [
        ("Engineering", "Strongly agree", "Good"),
        ("Support", "Strongly disagree", "Poor"),
        ("Sales", "Neutral", "Average"),
    ]:
        rows += f"{team},{satisfaction},{tooling}\n" * 30

    return ingest(survey, parse_upload((header + rows).encode(), "grouped.csv"))


@pytest.fixture
def logged_in(client: Client, owner: object) -> Client:
    client.force_login(owner)
    return client


class TestSharedJobInfrastructure:
    def test_the_two_layers_never_share_a_cache_key(self, grouped_dataset: object) -> None:
        """Same dataset, same plumbing, different analyses.

        A collision here would serve contingency tables as respondent groups.
        """
        assert relational.result_key(grouped_dataset.pk) != patterns.result_key(grouped_dataset.pk)
        assert relational.lock_key(grouped_dataset.pk) != patterns.lock_key(grouped_dataset.pk)

    def test_each_key_carries_its_own_engine_version(self, grouped_dataset: object) -> None:
        assert f"v{patterns.ENGINE_VERSION}" in patterns.result_key(grouped_dataset.pk)
        assert "patterns" in patterns.result_key(grouped_dataset.pk)

    def test_running_one_layer_does_not_mark_the_other_ready(self, grouped_dataset: object) -> None:
        patterns.compute_and_cache(grouped_dataset.pk)

        assert patterns.get_report(grouped_dataset).is_ready
        assert relational.get_report(grouped_dataset).status is JobStatus.NOT_STARTED


class TestJobLifecycle:
    def test_requesting_analysis_queues_one_job(self, grouped_dataset: object) -> None:
        with patch("apps.analytics.tasks.compute_pattern_analysis.delay") as queued:
            patterns.request_analysis(grouped_dataset)
            patterns.request_analysis(grouped_dataset)

        queued.assert_called_once_with(grouped_dataset.pk)

    def test_results_are_cached_after_the_job_runs(self, grouped_dataset: object) -> None:
        compute_pattern_analysis(grouped_dataset.pk)

        report = patterns.get_report(grouped_dataset)

        assert report.is_ready
        assert report.clusters.found_structure

    def test_the_task_reports_how_many_groups_it_found(self, grouped_dataset: object) -> None:
        found = compute_pattern_analysis(grouped_dataset.pk)

        assert found == 3

    def test_a_failure_releases_the_lock(self, grouped_dataset: object) -> None:
        cache.add(patterns.lock_key(grouped_dataset.pk), True, 600)

        with (
            patch(
                "apps.analytics.services.patterns.find_groups",
                side_effect=ValueError("boom"),
            ),
            pytest.raises(ValueError, match="boom"),
        ):
            compute_pattern_analysis(grouped_dataset.pk)

        assert cache.get(patterns.lock_key(grouped_dataset.pk)) is None

    def test_a_deleted_dataset_is_skipped(self, grouped_dataset: object) -> None:
        dataset_id = grouped_dataset.pk
        grouped_dataset.delete()

        assert compute_pattern_analysis(dataset_id) == 0


class TestPatternViews:
    def test_the_page_requires_login(self, client: Client, grouped_dataset: object) -> None:
        response = client.get(reverse("analytics:patterns", args=[grouped_dataset.pk]))

        assert response.status_code == 302

    def test_another_users_dataset_is_not_reachable(
        self, client: Client, grouped_dataset: object
    ) -> None:
        intruder = User.objects.create_user(email="other@example.com", password="correct-horse")
        client.force_login(intruder)

        response = client.get(reverse("analytics:patterns", args=[grouped_dataset.pk]))

        assert response.status_code == 404

    def test_a_first_visit_shows_the_working_state(
        self, logged_in: Client, grouped_dataset: object
    ) -> None:
        with patch("apps.analytics.tasks.compute_pattern_analysis.delay"):
            content = logged_in.get(
                reverse("analytics:patterns", args=[grouped_dataset.pk])
            ).content.decode()

        assert "Looking for groups" in content
        assert "data-poll-url" in content

    def test_finished_analysis_describes_each_group(
        self, logged_in: Client, grouped_dataset: object
    ) -> None:
        """A group is only useful if it can be described in answers."""
        patterns.compute_and_cache(grouped_dataset.pk)

        content = logged_in.get(
            reverse("analytics:patterns", args=[grouped_dataset.pk])
        ).content.decode()

        assert "Profile 1" in content
        assert "Times more likely" in content
        assert "Support" in content

    def test_results_carry_no_cats(self, logged_in: Client, grouped_dataset: object) -> None:
        patterns.compute_and_cache(grouped_dataset.pk)

        content = logged_in.get(
            reverse("analytics:patterns", args=[grouped_dataset.pk])
        ).content.decode()

        assert "cat-panel__art" not in content

    def test_the_api_answers_202_while_working_and_200_when_ready(
        self, logged_in: Client, grouped_dataset: object
    ) -> None:
        with patch("apps.analytics.tasks.compute_pattern_analysis.delay"):
            working = logged_in.get(reverse("analytics_api:patterns", args=[grouped_dataset.pk]))
        assert working.status_code == 202

        patterns.compute_and_cache(grouped_dataset.pk)
        ready = logged_in.get(reverse("analytics_api:patterns", args=[grouped_dataset.pk]))

        assert ready.status_code == 200
        assert ready.json()["clusters"]["found_structure"] is True

    def test_absence_of_groups_is_explained_not_hidden(
        self, logged_in: Client, survey: object, csv_file: bytes
    ) -> None:
        """Refusing to invent groups is a finding, and the page has to say so
        or it reads as a broken analysis.
        """
        small = ingest(survey, parse_upload(csv_file, "small.csv"))
        patterns.compute_and_cache(small.pk)

        content = logged_in.get(reverse("analytics:patterns", args=[small.pk])).content.decode()

        assert "No distinct respondent groups" in content
        assert "Too few respondents" in content

    def test_the_page_explains_polarized_versus_divided(
        self, logged_in: Client, grouped_dataset: object
    ) -> None:
        """The distinction is the whole point of the measure, and it is not
        self-evident from the word alone.
        """
        patterns.compute_and_cache(grouped_dataset.pk)

        content = logged_in.get(
            reverse("analytics:patterns", args=[grouped_dataset.pk])
        ).content.decode()

        assert "two camps" in content
        assert "has not settled" in content
