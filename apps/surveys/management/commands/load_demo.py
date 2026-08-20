"""Create a demo account and ingest the sample exports.

Opt-in, and never run by a migration: a fixture account that appears on every
deploy is a credential nobody chose to create. The command refuses outright
when DEBUG is off, so a production database cannot grow a known password by
someone running the wrong command in the wrong shell.
"""

from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.surveys.models import Survey
from apps.surveys.services.ingestion import ingest
from apps.surveys.services.parsing import parse_upload

DEMO_EMAIL = "demo@example.com"
# Deliberately hardcoded and published in the README, so the project can be
# evaluated without a signup. The rule flagging it is right in general, which is
# why the exemption is stated here rather than widened in the linter config:
# the guard below is what keeps this out of a real database.
DEMO_PASSWORD = "gato-analitico-99"  # noqa: S105

SAMPLES = [
    ("01-clear-relationship.csv", "Employee engagement 2026"),
    ("02-distinct-groups.csv", "Encuesta de clima laboral"),
    ("03-no-findings.csv", "Event feedback"),
]


class Command(BaseCommand):
    help = "Create the demo account and load the sample surveys."

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "load_demo refuses to run with DEBUG off. It creates an account "
                "with a published password, which belongs in development only."
            )

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            email=DEMO_EMAIL, defaults={"display_name": "Demo"}
        )
        user.set_password(DEMO_PASSWORD)
        user.save()
        self.stdout.write(f"{'Created' if created else 'Updated'} {DEMO_EMAIL}")

        samples = Path(settings.BASE_DIR) / "samples"

        for filename, survey_name in SAMPLES:
            path = samples / filename
            if not path.exists():
                self.stdout.write(self.style.WARNING(f"Missing {path}, skipping"))
                continue

            # Re-running replaces the demo data rather than stacking versions,
            # so the account always looks the way the README describes it.
            Survey.objects.filter(owner=user, name=survey_name).delete()
            survey = Survey.objects.create(owner=user, name=survey_name)
            dataset = ingest(survey, parse_upload(path.read_bytes(), filename))

            self.stdout.write(
                f"  {survey_name}: {dataset.respondent_count} respondents, "
                f"{dataset.question_count} questions"
            )

        self.stdout.write(self.style.SUCCESS(f"\nSign in as {DEMO_EMAIL} / {DEMO_PASSWORD}"))
