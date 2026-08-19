"""Project package.

The Celery app is imported here so that ``@shared_task`` decorators in feature
apps bind to it as soon as Django starts.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
