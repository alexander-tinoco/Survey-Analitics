"""Tests for the demo data loader."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command

from apps.surveys.models import Survey

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def development(settings: object) -> None:
    """Django forces DEBUG off during tests, and the command refuses to run
    without it — which is the guard working. These tests exercise the path
    the command actually takes in development.
    """
    settings.DEBUG = True


def test_it_creates_the_documented_account(development: None) -> None:
    """The README publishes these credentials, so they have to be these."""
    call_command("load_demo")

    user = User.objects.get(email="demo@example.com")
    assert user.check_password("gato-analitico-99")


def test_it_loads_every_sample(development: None) -> None:
    call_command("load_demo")

    user = User.objects.get(email="demo@example.com")
    assert user.surveys.count() == 3
    assert all(survey.datasets.exists() for survey in user.surveys.all())


def test_running_it_twice_replaces_rather_than_stacks(development: None) -> None:
    """The account should always look the way the README describes it."""
    call_command("load_demo")
    call_command("load_demo")

    user = User.objects.get(email="demo@example.com")
    assert user.surveys.count() == 3
    assert all(survey.datasets.count() == 1 for survey in user.surveys.all())


def test_it_refuses_to_run_with_debug_off(settings: object) -> None:
    """A fixture account with a published password must not be creatable on a
    production database by someone running the wrong command.
    """
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DEBUG off"):
        call_command("load_demo")

    assert not Survey.objects.exists()
