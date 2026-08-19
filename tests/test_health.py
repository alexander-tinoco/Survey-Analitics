"""Tests for the project-level health endpoint."""

import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_health_reports_ok_when_database_is_reachable(client: Client) -> None:
    """A healthy process with a working database answers 200."""
    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.django_db
def test_health_reports_unhealthy_when_database_is_unreachable(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process that cannot reach the database answers 503, not 200.

    This is the case that matters: an orchestrator must not keep routing
    traffic to a container that can serve HTML but not read any data.
    """

    def fail() -> None:
        raise OSError("connection refused")

    monkeypatch.setattr("config.views.connection.ensure_connection", fail)

    response = client.get(reverse("health"))

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
