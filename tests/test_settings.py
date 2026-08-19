"""Guards on configuration that would be expensive to get wrong."""

from django.conf import settings


def test_secret_key_is_not_hardcoded_in_the_repository() -> None:
    """The key must come from the environment, not from version control."""
    assert settings.SECRET_KEY
    assert "django-insecure" not in settings.SECRET_KEY


def test_api_requires_authentication_by_default() -> None:
    """Endpoints are closed unless a view opts out, not open unless it opts in.

    A permissive default means one forgotten decorator exposes data; a strict
    default means one forgotten decorator returns 403, which is noisy and safe.
    """
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == (
        "rest_framework.permissions.IsAuthenticated",
    )


def test_api_accepts_both_tokens_and_sessions() -> None:
    """JWT for API clients, sessions for the server-rendered pages.

    JWT is listed first so an unauthenticated call answers 401 with a
    challenge header rather than a bare 403 — the order is the behaviour,
    not a formatting detail.
    """
    classes = settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]

    assert classes[0].endswith("JWTAuthentication")
    assert any(c.endswith("SessionAuthentication") for c in classes)


def test_list_endpoints_are_paginated() -> None:
    """Without a default page size, one large dataset can exhaust memory."""
    assert settings.REST_FRAMEWORK["PAGE_SIZE"] > 0
