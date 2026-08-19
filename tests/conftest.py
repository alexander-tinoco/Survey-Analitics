"""Fixtures shared across the test suite."""

import pytest
from django.test import Client


@pytest.fixture
def client() -> Client:
    """An unauthenticated Django test client."""
    return Client()
