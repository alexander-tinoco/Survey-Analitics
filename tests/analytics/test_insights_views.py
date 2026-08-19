"""Tests for the findings page and its API."""

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

        response = client.get(reverse("analytics:insights", args=[linked_dataset.pk]))

        assert response.status_code == 404

    def test_the_api_requires_authentication(self, client: Client, linked_dataset: object) -> None:
        response = client.get(reverse("analytics_api:insights", args=[linked_dataset.pk]))

        assert response.status_code == 401


class TestFindings:
    def test_the_page_states_the_relationship_in_plain_language(
        self, logged_in: Client, linked_dataset: object
    ) -> None:
        """The product brief's example, rendered end to end from a real file."""
        prepare(linked_dataset)

        content = logged_in.get(
            reverse("analytics:insights", args=[linked_dataset.pk])
        ).content.decode()

        assert "80.0%" in content
        assert "45.0%" in content
        assert "Unsatisfied" in content

    def test_findings_are_ordered_by_relevance(
        self, logged_in: Client, linked_dataset: object
    ) -> None:
        prepare(linked_dataset)

        body = logged_in.get(reverse("analytics_api:insights", args=[linked_dataset.pk])).json()

        relevances = [insight["relevance"] for insight in body["insights"]]
        assert relevances == sorted(relevances, reverse=True)

    def test_every_finding_carries_its_evidence(
        self, logged_in: Client, linked_dataset: object
    ) -> None:
        """A claim the reader cannot check is a claim they should not trust."""
        prepare(linked_dataset)

        body = logged_in.get(reverse("analytics_api:insights", args=[linked_dataset.pk])).json()

        for insight in body["insights"]:
            assert insight["evidence"]
            assert insight["questions"]

    def test_the_page_explains_what_was_left_out(
        self, logged_in: Client, linked_dataset: object
    ) -> None:
        """Readers should know the list is filtered, not exhaustive."""
        prepare(linked_dataset)

        # Whitespace-collapsed: the template wraps these sentences across
        # lines, and asserting on the wrapped form would break on reflow.
        content = " ".join(
            logged_in.get(reverse("analytics:insights", args=[linked_dataset.pk]))
            .content.decode()
            .split()
        )

        assert "failed its statistical assumptions" in content
        assert "correcting for the number of comparisons made" in content


class TestIncompleteState:
    def test_pending_layers_are_named_not_hidden(
        self, logged_in: Client, linked_dataset: object
    ) -> None:
        """ "Nothing found" and "not finished" must not look the same."""
        from unittest.mock import patch

        with (
            patch("apps.analytics.tasks.compute_relational_analysis.delay"),
            patch("apps.analytics.tasks.compute_pattern_analysis.delay"),
        ):
            content = logged_in.get(
                reverse("analytics:insights", args=[linked_dataset.pk])
            ).content.decode()

        assert "Still working on" in content
        assert "relationships and groups" in content
        assert "data-poll-url" in content

    def test_the_api_answers_202_until_every_layer_is_ready(
        self, logged_in: Client, linked_dataset: object
    ) -> None:
        from unittest.mock import patch

        with (
            patch("apps.analytics.tasks.compute_relational_analysis.delay"),
            patch("apps.analytics.tasks.compute_pattern_analysis.delay"),
        ):
            pending = logged_in.get(reverse("analytics_api:insights", args=[linked_dataset.pk]))
        assert pending.status_code == 202
        assert pending.json()["complete"] is False

        prepare(linked_dataset)
        ready = logged_in.get(reverse("analytics_api:insights", args=[linked_dataset.pk]))

        assert ready.status_code == 200
        assert ready.json()["complete"] is True

    def test_visiting_the_page_starts_the_work(
        self, logged_in: Client, linked_dataset: object
    ) -> None:
        from unittest.mock import patch

        with (
            patch("apps.analytics.tasks.compute_relational_analysis.delay") as relational_job,
            patch("apps.analytics.tasks.compute_pattern_analysis.delay") as pattern_job,
        ):
            logged_in.get(reverse("analytics:insights", args=[linked_dataset.pk]))

        relational_job.assert_called_once_with(linked_dataset.pk)
        pattern_job.assert_called_once_with(linked_dataset.pk)


class TestNothingToReport:
    def test_an_empty_result_is_stated_as_a_finding(self, logged_in: Client, owner: object) -> None:
        """Silence is a correct output, and the page has to say so plainly or
        it reads as a broken analysis.
        """
        import numpy as np

        generator = np.random.default_rng(seed=17)
        survey = Survey.objects.create(owner=owner, name="Random survey")
        rows = "Q1,Q2,Q3\n" + "".join(
            ",".join(generator.choice(["a", "b", "c"], 3)) + "\n" for _ in range(150)
        )
        dataset = ingest(survey, parse_upload(rows.encode(), "random.csv"))
        prepare(dataset)

        content = logged_in.get(reverse("analytics:insights", args=[dataset.pk])).content.decode()

        report = insights.build(dataset)
        assert report.insights == []
        assert "Nothing stands out" in content
        assert "img/cat404.png" in content

    def test_the_empty_state_is_the_only_place_a_cat_appears(
        self, logged_in: Client, linked_dataset: object
    ) -> None:
        prepare(linked_dataset)

        content = logged_in.get(
            reverse("analytics:insights", args=[linked_dataset.pk])
        ).content.decode()

        assert "cat-panel__art" not in content
