"""Guards on the production security posture.

These settings only take effect on a deployed instance, which means a mistake in
them is invisible during development and expensive in production. Loading the
module in a test is the cheapest place to catch a regression.
"""

import importlib
from types import ModuleType

import pytest


@pytest.fixture
def production_settings(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import the production settings module with the environment it expects."""
    monkeypatch.setenv("DJANGO_SECRET_KEY", "a-sufficiently-long-production-secret-key")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "surveyanalytics.example.com")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@db:5432/app")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")

    module = importlib.import_module("config.settings.production")
    return importlib.reload(module)


def test_debug_is_disabled(production_settings: ModuleType) -> None:
    """DEBUG in production leaks stack traces, settings, and SQL to visitors."""
    assert production_settings.DEBUG is False


def test_allowed_hosts_comes_from_the_environment(production_settings: ModuleType) -> None:
    """A wildcard here enables Host header poisoning."""
    assert production_settings.ALLOWED_HOSTS == ["surveyanalytics.example.com"]
    assert "*" not in production_settings.ALLOWED_HOSTS


def test_traffic_is_forced_onto_https(production_settings: ModuleType) -> None:
    assert production_settings.SECURE_SSL_REDIRECT is True
    assert production_settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


def test_cookies_are_not_sent_over_plain_http(production_settings: ModuleType) -> None:
    """Session and CSRF cookies over HTTP can be captured in transit."""
    assert production_settings.SESSION_COOKIE_SECURE is True
    assert production_settings.CSRF_COOKIE_SECURE is True


def test_hsts_is_enabled_for_at_least_a_year(production_settings: ModuleType) -> None:
    """A short max-age leaves a window for downgrade attacks on first contact."""
    assert production_settings.SECURE_HSTS_SECONDS >= 31_536_000
    assert production_settings.SECURE_HSTS_INCLUDE_SUBDOMAINS is True


def test_clickjacking_and_mime_sniffing_are_blocked(production_settings: ModuleType) -> None:
    assert production_settings.X_FRAME_OPTIONS == "DENY"
    assert production_settings.SECURE_CONTENT_TYPE_NOSNIFF is True
