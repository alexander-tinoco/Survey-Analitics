"""Tests for the cat error pages.

Each handler must keep its real status code. A friendly page served with a 200
tells crawlers and uptime monitors that a broken URL is working.

The handlers are exercised directly as well as through the URL conf: they only
run once something else has already gone wrong, which is the worst moment to
discover that the error page itself raises.
"""

import pytest
from django.test import Client, RequestFactory

from config.error_views import bad_request, permission_denied, server_error


@pytest.mark.django_db
def test_unknown_url_returns_404_with_its_cat(client: Client) -> None:
    response = client.get("/no-such-page/")

    assert response.status_code == 404
    assert "img/cat404.png" in response.content.decode()


@pytest.mark.django_db
def test_error_pages_render_directly(client: Client) -> None:
    """Render each template so a broken tag fails in CI, not in production."""
    from django.template.loader import render_to_string

    for template, asset in [
        ("errors/400.html", "img/cat400.png"),
        ("errors/401.html", "img/cat401.png"),
        ("errors/404.html", "img/cat404.png"),
        ("errors/500.html", "img/cat400.png"),
    ]:
        html = render_to_string(template)
        assert asset in html


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("handler", "expected_status", "asset"),
    [
        (bad_request, 400, "img/cat400.png"),
        (permission_denied, 403, "img/cat401.png"),
        (server_error, 500, "img/cat400.png"),
    ],
)
def test_handler_returns_its_status_and_cat(
    handler: object, expected_status: int, asset: str
) -> None:
    request = RequestFactory().get("/anything/")

    response = handler(request) if handler is server_error else handler(request, None)

    assert response.status_code == expected_status
    assert asset in response.content.decode()
