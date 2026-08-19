"""Tests for caching, queueing and the async job around relational analysis."""

from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.analytics.services import relational
from apps.analytics.services.relational import JobStatus
from apps.analytics.tasks import compute_relational_analysis
from apps.surveys.models import Dataset
from apps.surveys.services.ingestion import ingest
from apps.surveys.services.parsing import parse_upload

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache() -> None:
    """Redis is shared between tests; leftovers would leak between them."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def dataset(survey: object, csv_file: bytes) -> Dataset:
    return ingest(survey, parse_upload(csv_file, "survey.csv"))


class TestCacheKeys:
    def test_each_dataset_gets_its_own_key(self, survey: object, csv_file: bytes) -> None:
        """Two uploads must never share cached results."""
        first = ingest(survey, parse_upload(csv_file, "first.csv"))
        second = ingest(survey, parse_upload(csv_file, "second.csv"))

        assert relational.result_key(first.pk) != relational.result_key(second.pk)

    def test_the_key_carries_the_engine_version(self, dataset: Dataset) -> None:
        """Bumping the engine invalidates every cached result at once.

        The data did not change but its meaning did, and a dataset id alone
        cannot express that.
        """
        assert f"v{relational.ENGINE_VERSION}" in relational.result_key(dataset.pk)

    def test_re_uploading_cannot_serve_stale_results(self, survey: object, csv_file: bytes) -> None:
        """The payoff of immutable, versioned datasets (ADR 0002).

        A re-upload produces a new dataset with a new id, so the old key is
        simply never read again. There is no invalidation step to forget.
        """
        first = ingest(survey, parse_upload(csv_file, "first.csv"))
        relational.compute_and_cache(first.pk)
        assert relational.get_report(first).is_ready

        second = ingest(survey, parse_upload(csv_file, "second.csv"))

        assert relational.get_report(second).status is JobStatus.NOT_STARTED


class TestJobLifecycle:
    def test_an_unanalyzed_dataset_reports_not_started(self, dataset: Dataset) -> None:
        assert relational.get_report(dataset).status is JobStatus.NOT_STARTED

    def test_requesting_analysis_queues_exactly_one_job(self, dataset: Dataset) -> None:
        with patch("apps.analytics.tasks.compute_relational_analysis.delay") as queued:
            relational.request_analysis(dataset)

        queued.assert_called_once_with(dataset.pk)

    def test_a_second_request_does_not_queue_a_duplicate(self, dataset: Dataset) -> None:
        """cache.add is atomic in Redis, so two simultaneous visitors cannot
        both win the lock and start the same job twice.
        """
        with patch("apps.analytics.tasks.compute_relational_analysis.delay") as queued:
            relational.request_analysis(dataset)
            relational.request_analysis(dataset)
            relational.request_analysis(dataset)

        assert queued.call_count == 1

    def test_a_running_job_is_reported_as_running(self, dataset: Dataset) -> None:
        with patch("apps.analytics.tasks.compute_relational_analysis.delay"):
            relational.request_analysis(dataset)

        assert relational.get_report(dataset).status is JobStatus.RUNNING

    def test_results_are_cached_after_the_job_runs(self, dataset: Dataset) -> None:
        relational.compute_and_cache(dataset.pk)

        report = relational.get_report(dataset)

        assert report.is_ready
        assert report.associations

    def test_the_lock_is_released_only_after_the_result_is_stored(self, dataset: Dataset) -> None:
        """Otherwise a poller sees a window with neither lock nor result and
        queues a duplicate job.
        """
        relational.compute_and_cache(dataset.pk)

        assert cache.get(relational.lock_key(dataset.pk)) is None
        assert cache.get(relational.result_key(dataset.pk)) is not None

    def test_a_cached_dataset_is_never_recomputed(self, dataset: Dataset) -> None:
        relational.compute_and_cache(dataset.pk)

        with patch("apps.analytics.services.relational.analyze") as recomputed:
            report = relational.get_report(dataset)

        recomputed.assert_not_called()
        assert report.is_ready


class TestTask:
    def test_the_task_computes_and_reports_how_many_it_found(self, dataset: Dataset) -> None:
        found = compute_relational_analysis(dataset.pk)

        assert found == len(relational.get_report(dataset).associations)
        assert relational.get_report(dataset).is_ready

    def test_a_deleted_dataset_is_skipped_without_retrying(self, dataset: Dataset) -> None:
        """The work is no longer wanted, which is not a failure."""
        dataset_id = dataset.pk
        dataset.delete()

        assert compute_relational_analysis(dataset_id) == 0

    def test_a_failure_releases_the_lock(self, dataset: Dataset) -> None:
        """A permanent failure must not leave the dataset looking busy forever."""
        cache.add(relational.lock_key(dataset.pk), True, 600)

        with (
            patch(
                "apps.analytics.services.relational.analyze",
                side_effect=ValueError("boom"),
            ),
            pytest.raises(ValueError, match="boom"),
        ):
            compute_relational_analysis(dataset.pk)

        assert cache.get(relational.lock_key(dataset.pk)) is None


class TestReportContents:
    def test_only_surviving_associations_count_as_significant(self, dataset: Dataset) -> None:
        relational.compute_and_cache(dataset.pk)
        report = relational.get_report(dataset)

        assert all(a.is_significant for a in report.significant)
        assert len(report.significant) <= len(report.associations)

    def test_rendered_tables_pair_counts_with_their_percentages(self, dataset: Dataset) -> None:
        """Templates cannot index into a list, so the rendering zips them."""
        relational.compute_and_cache(dataset.pk)
        association = relational.get_report(dataset).associations[0]

        rendered = relational.association_to_dict(association)
        first_row = rendered["table"]["rows"][0]

        assert len(first_row["cells"]) == len(rendered["table"]["column_labels"])
        assert first_row["total"] == sum(cell["count"] for cell in first_row["cells"])
