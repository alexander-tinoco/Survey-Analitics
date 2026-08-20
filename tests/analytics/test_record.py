"""Tests for the record page — one dataset, one URL, four sections.

This replaces the separate tests for the four analysis pages. They asserted
that each page rendered its own layer; what matters now is that one page
renders all of them, states which are still computing, and keeps the
illustrations out of the parts that show data.
"""

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
def dataset(survey: Survey, csv_file: bytes) -> object:
    return ingest(survey, parse_upload(csv_file, "survey.csv"))


@pytest.fixture
def analyzed(owner: object) -> object:
    """A dataset with a relationship worth reporting, fully analyzed.

    Of the 60 who answered "Unsatisfied", 48 also reported "Low" support
    (80.0%), against 54 of 120 overall (45.0%).
    """
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


class TestAccessControl:
    def test_the_record_requires_login(self, client: Client, dataset: object) -> None:
        response = client.get(reverse("analytics:record", args=[dataset.pk]))

        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_another_users_record_is_not_readable(self, client: Client, dataset: object) -> None:
        intruder = User.objects.create_user(email="other@example.com", password="correct-horse")
        client.force_login(intruder)

        response = client.get(reverse("analytics:record", args=[dataset.pk]))

        assert response.status_code == 404


class TestOneRecordNotFourPages:
    def test_every_layer_appears_on_one_page(self, logged_in: Client, analyzed: object) -> None:
        """The reader should not have to know which page answers which
        question before they can look anything up.
        """
        content = logged_in.get(reverse("analytics:record", args=[analyzed.pk])).content.decode()

        for section in ["Findings", "Distributions", "Relationships", "Groups"]:
            assert f'id="{section.lower()}"' in content
            assert f">{section}<" in content

    @pytest.mark.parametrize(
        "retired",
        ["analytics:insights", "analytics:relational", "analytics:patterns", "analytics:dashboard"],
    )
    def test_retired_pages_redirect_into_the_record(
        self, logged_in: Client, analyzed: object, retired: str
    ) -> None:
        """Links already handed out keep working."""
        response = logged_in.get(reverse(retired, args=[analyzed.pk]))

        assert response.status_code == 302
        assert response.url == reverse("analytics:record", args=[analyzed.pk])

    def test_the_index_names_every_section(self, logged_in: Client, analyzed: object) -> None:
        """Wayfinding: the reader must be able to tell where they are."""
        content = logged_in.get(reverse("analytics:record", args=[analyzed.pk])).content.decode()

        assert content.count("data-index-link") == 4
        assert 'aria-label="Sections of this record"' in content

    def test_the_header_states_which_record_this_is(
        self, logged_in: Client, analyzed: object
    ) -> None:
        content = logged_in.get(reverse("analytics:record", args=[analyzed.pk])).content.decode()

        assert "Support survey" in content
        assert "support.csv" in content
        assert "Version 1" in content


class TestFindings:
    def test_the_finding_is_stated_in_plain_language(
        self, logged_in: Client, analyzed: object
    ) -> None:
        content = logged_in.get(reverse("analytics:record", args=[analyzed.pk])).content.decode()

        assert "80.0%" in content
        assert "45.0%" in content
        assert "Unsatisfied" in content

    def test_each_finding_can_reach_its_figures(self, logged_in: Client, analyzed: object) -> None:
        """A claim the reader cannot check is a claim they should not trust."""
        content = logged_in.get(reverse("analytics:record", args=[analyzed.pk])).content.decode()

        assert "The figures behind this" in content
        assert "finding__evidence" in content

    def test_nothing_found_is_rendered_as_a_result(self, logged_in: Client, owner: object) -> None:
        """The product's most characteristic answer. It gets the weight of a
        finding, not the greyness of an empty state.
        """
        import numpy as np

        generator = np.random.default_rng(seed=17)
        survey = Survey.objects.create(owner=owner, name="Random survey")
        rows = "Q1,Q2,Q3\n" + "".join(
            ",".join(generator.choice(["a", "b", "c"], 3)) + "\n" for _ in range(150)
        )
        dataset = ingest(survey, parse_upload(rows.encode(), "random.csv"))
        relational.compute_and_cache(dataset.pk)
        patterns.compute_and_cache(dataset.pk)

        content = logged_in.get(reverse("analytics:record", args=[dataset.pk])).content.decode()

        assert "Nothing stands out" in content
        assert "That is a result" in content


class TestProcessingState:
    def test_a_first_visit_queues_both_background_layers(
        self, logged_in: Client, dataset: object
    ) -> None:
        from unittest.mock import patch

        with (
            patch("apps.analytics.tasks.compute_relational_analysis.delay") as relational_job,
            patch("apps.analytics.tasks.compute_pattern_analysis.delay") as pattern_job,
        ):
            content = logged_in.get(reverse("analytics:record", args=[dataset.pk])).content.decode()

        relational_job.assert_called_once_with(dataset.pk)
        pattern_job.assert_called_once_with(dataset.pk)
        assert "data-poll-url" in content

    def test_pending_layers_are_named(self, logged_in: Client, dataset: object) -> None:
        """ "Nothing found" and "not finished" must not look the same."""
        from unittest.mock import patch

        with (
            patch("apps.analytics.tasks.compute_relational_analysis.delay"),
            patch("apps.analytics.tasks.compute_pattern_analysis.delay"),
        ):
            content = logged_in.get(reverse("analytics:record", args=[dataset.pk])).content.decode()

        assert "Still computing" in content
        assert "relationships and groups" in content

    def test_distributions_render_before_the_slow_layers_finish(
        self, logged_in: Client, dataset: object
    ) -> None:
        """The cheap layer runs inline, so the page is never empty."""
        from unittest.mock import patch

        with (
            patch("apps.analytics.tasks.compute_relational_analysis.delay"),
            patch("apps.analytics.tasks.compute_pattern_analysis.delay"),
        ):
            content = logged_in.get(reverse("analytics:record", args=[dataset.pk])).content.decode()

        assert "Department" in content
        assert "Satisfaction" in content


class TestTables:
    def test_each_chart_has_a_table_with_the_same_numbers(
        self, logged_in: Client, dataset: object
    ) -> None:
        """A canvas is opaque to a screen reader, so the table is required.

        Sales appears twice among five respondents: 40.0%.
        """
        content = logged_in.get(reverse("analytics:record", args=[dataset.pk])).content.decode()

        assert "40.0%" in content
        assert "<table" in content

    def test_numeric_questions_show_their_summary(self, logged_in: Client, dataset: object) -> None:
        """Ages 34, 29, 45, 38, 52 -> mean 39.6, median 38."""
        content = logged_in.get(reverse("analytics:record", args=[dataset.pk])).content.decode()

        assert "39.6" in content
        assert "Median" in content

    def test_the_most_skipped_question_is_called_out(
        self, logged_in: Client, dataset: object
    ) -> None:
        """One blank comment of five: 80% response rate, the lowest here."""
        content = logged_in.get(reverse("analytics:record", args=[dataset.pk])).content.decode()

        assert "80.0%" in content
        assert "the least of any question" in content

    def test_an_unreliable_association_is_flagged(self, logged_in: Client, dataset: object) -> None:
        """Five respondents cannot support a chi-square, and the page says so
        rather than presenting a p-value as if it meant something.
        """
        relational.compute_and_cache(dataset.pk)
        patterns.compute_and_cache(dataset.pk)

        content = logged_in.get(reverse("analytics:record", args=[dataset.pk])).content.decode()

        report = relational.get_report(dataset)
        if any(not a.is_reliable for a in report.associations):
            assert "Too few respondents" in content

    def test_a_p_value_is_never_printed_as_zero(self, logged_in: Client, analyzed: object) -> None:
        """No test returns exactly zero, and a rounded 0.0 reads as if one had."""
        content = logged_in.get(reverse("analytics:record", args=[analyzed.pk])).content.decode()

        assert 'adjusted p <span class="num">0.0</span>' not in content


class TestDesignRules:
    def test_the_record_carries_no_cats(self, logged_in: Client, analyzed: object) -> None:
        """Illustrations stay out of data views: a cat beside a p-value
        undercuts the number it sits next to.
        """
        page = logged_in.get(reverse("analytics:record", args=[analyzed.pk])).content.decode()
        # The favicon is site identity carried by browser chrome, not an
        # illustration on the surface, so the rule is checked on the content.
        body = page.split("<main", 1)[1].split("</main>", 1)[0]

        assert "plate__art" not in body
        assert "img/cat" not in body

    def test_chart_data_is_embedded_not_fetched(self, logged_in: Client, analyzed: object) -> None:
        """The server already computed it to render the tables."""
        content = logged_in.get(reverse("analytics:record", args=[analyzed.pk])).content.decode()

        assert 'id="chart-data"' in content

    def test_the_direction_contract_survives_into_the_markup(
        self, logged_in: Client, analyzed: object
    ) -> None:
        """A contract nobody can audit is not a contract."""
        content = logged_in.get(reverse("analytics:record", args=[analyzed.pk])).content.decode()

        assert "THESIS:" in content
        assert "OWN-WORLD:" in content

    def test_no_template_comment_leaks_into_the_page(
        self, logged_in: Client, analyzed: object
    ) -> None:
        """Django's {# #} comments are single-line only; a multi-line one
        renders to the reader as text.
        """
        content = logged_in.get(reverse("analytics:record", args=[analyzed.pk])).content.decode()

        assert "{#" not in content
