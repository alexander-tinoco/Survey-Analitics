"""Error page handlers.

Django's defaults look for ``400.html``, ``403.html``, ``404.html`` and
``500.html`` at the template root. These live under ``templates/errors/``
instead, so each status needs an explicit handler.

Every response keeps its real status code. Rendering a friendly page with a
200 would tell crawlers and monitoring that a broken URL is fine.
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def bad_request(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/400.html", status=400)


def permission_denied(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    """Serve the gatekeeper cat for 403.

    Django has no 401 handler — an unauthenticated visitor is redirected to
    the login page instead — so the same illustration covers the case that
    does reach a page: authenticated, but not allowed through.
    """
    return render(request, "errors/401.html", status=403)


def page_not_found(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def server_error(request: HttpRequest) -> HttpResponse:
    """Render the 500 page.

    Uses ``render`` rather than a context-free template load so the header
    still resolves. A failure here would replace the error page with another
    error, so the template it points at must stay free of database access.
    """
    return render(request, "errors/500.html", status=500)
