"""Shared plumbing for cached, worker-computed analyses.

Both the relational and pattern layers need the same thing: run something
expensive on a worker, cache the result, and let a page ask whether it is
ready without ever computing inline. That logic is subtle enough — atomic
locking, releasing the lock only after the result is stored, releasing it on
failure — that having two copies would mean fixing every bug twice.

The cache key is safe because of ADR 0002: datasets are immutable and
versioned, so a re-upload produces a new id and the old key is simply never
read again. There is no invalidation step to forget.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, TypeVar

from django.core.cache import cache

from apps.surveys.models import Dataset

logger = logging.getLogger(__name__)

# Results are deterministic for an immutable dataset, so this is a memory
# bound rather than a freshness one: an expired entry is recomputed and comes
# back identical.
RESULT_TTL_SECONDS = 7 * 24 * 60 * 60

# Long enough that a slow job is not queued twice, short enough that a worker
# lost mid-job does not leave a dataset stuck looking busy for an hour.
LOCK_TTL_SECONDS = 10 * 60

Payload = TypeVar("Payload")


class JobStatus(StrEnum):
    """What the caller should do next."""

    READY = "ready"
    RUNNING = "running"
    NOT_STARTED = "not_started"


@dataclass(frozen=True)
class JobResult(Generic[Payload]):
    """Either a finished analysis or the state of the job producing one."""

    status: JobStatus
    payload: Payload | None = None

    @property
    def is_ready(self) -> bool:
        return self.status is JobStatus.READY


class CachedAnalysis(Generic[Payload]):
    """One kind of analysis, cached per dataset and computed on a worker.

    ``version`` is bumped when the statistics change: the data is unchanged
    but its meaning is not, and a dataset id alone cannot express that.
    """

    def __init__(
        self,
        name: str,
        version: int,
        compute: Callable[[Dataset], Payload],
        enqueue: Callable[[int], Any],
    ) -> None:
        self.name = name
        self.version = version
        self._compute = compute
        self._enqueue = enqueue

    def result_key(self, dataset_id: int) -> str:
        return f"analytics:{self.name}:v{self.version}:dataset:{dataset_id}"

    def lock_key(self, dataset_id: int) -> str:
        return f"analytics:{self.name}:v{self.version}:lock:{dataset_id}"

    def get(self, dataset: Dataset) -> JobResult[Payload]:
        """Read cached results, or report that a job is running.

        Never computes inline: a request that blocks on the analysis is
        exactly what the worker exists to prevent.
        """
        cached = cache.get(self.result_key(dataset.pk))
        if cached is not None:
            return JobResult(status=JobStatus.READY, payload=cached)

        running = cache.get(self.lock_key(dataset.pk)) is not None
        return JobResult(status=JobStatus.RUNNING if running else JobStatus.NOT_STARTED)

    def request(self, dataset: Dataset) -> JobResult[Payload]:
        """Ensure results exist, or that a job is on its way to producing them."""
        result = self.get(dataset)
        if result.status is not JobStatus.NOT_STARTED:
            return result

        # cache.add is atomic in Redis: it sets the key only when absent, so
        # two simultaneous requests cannot both win and queue the same job.
        if cache.add(self.lock_key(dataset.pk), True, LOCK_TTL_SECONDS):
            self._enqueue(dataset.pk)

        return JobResult(status=JobStatus.RUNNING)

    def compute_and_cache(self, dataset_id: int) -> Payload:
        """Run the analysis and store it. Called by the worker, not a view."""
        dataset = Dataset.objects.get(pk=dataset_id)
        payload = self._compute(dataset)

        cache.set(self.result_key(dataset_id), payload, RESULT_TTL_SECONDS)
        # Released only after the result is stored, so a poller never sees a
        # window with neither a lock nor a result and queues a duplicate.
        cache.delete(self.lock_key(dataset_id))

        return payload

    def clear(self, dataset_id: int) -> None:
        """Drop any cached result and lock for a dataset."""
        cache.delete_many([self.result_key(dataset_id), self.lock_key(dataset_id)])
