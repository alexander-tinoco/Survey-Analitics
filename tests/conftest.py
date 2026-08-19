"""Fixtures shared across the test suite."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.surveys.models import Survey

User = get_user_model()


@pytest.fixture
def client() -> Client:
    """An unauthenticated Django test client."""
    return Client()


@pytest.fixture
def owner() -> object:
    """A user who owns surveys."""
    return User.objects.create_user(email="owner@example.com", password="correct-horse-battery")


@pytest.fixture
def survey(owner: object) -> Survey:
    return Survey.objects.create(owner=owner, name="Employee survey")


@pytest.fixture
def csv_file() -> bytes:
    """A small export covering every inferred question type.

    Shared rather than redefined per package: ingestion, analytics and the
    view tests all need the same shape, and three copies would drift.
    """
    return (
        b"Age,Department,Satisfaction,Comments\n"
        b"34,Sales,Agree,The onboarding could have been faster\n"
        b"29,Engineering,Strongly agree,I would like more training options\n"
        b"45,Sales,Disagree,\n"
        b"38,Support,Neutral,Nothing much to add about this\n"
        b"52,Engineering,Agree,More flexible hours would help a lot\n"
    )
