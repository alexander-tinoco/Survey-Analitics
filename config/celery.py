"""Celery application.

Heavy analytics jobs (correlation matrices, clustering) run here instead of
blocking a request. Tasks are discovered from every installed app.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("surveyanalytics")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
