"""Background jobs for the analytics layers."""

import logging

from celery import shared_task

from apps.surveys.models import Dataset

from .services import relational

logger = logging.getLogger(__name__)


@shared_task(
    # Retried because the usual failure is transient: a worker starting
    # before Postgres is reachable, or a dropped connection mid-query.
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    # The dataset id, not the model instance: a pickled instance would carry
    # a snapshot of the row into the queue and go stale there.
    name="analytics.compute_relational_analysis",
)
def compute_relational_analysis(dataset_id: int) -> int:
    """Cross-tabulate every testable pair of questions in a dataset.

    Returns the number of associations found, which is what shows up in the
    worker log — enough to tell a finished job from a job that found nothing.
    """
    try:
        associations = relational.compute_and_cache(dataset_id)
    except Dataset.DoesNotExist:
        # The dataset was deleted between queueing and running. Not an error
        # worth retrying: the work is simply no longer wanted.
        logger.info("Dataset %s no longer exists; skipping analysis", dataset_id)
        relational.clear(dataset_id)
        return 0
    except Exception:
        # Release the lock before the retry so a permanent failure does not
        # leave the dataset looking permanently busy.
        relational.clear(dataset_id)
        raise

    logger.info("Analyzed dataset %s: %s associations", dataset_id, len(associations))
    return len(associations)
