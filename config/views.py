"""Project-level views that belong to no feature app."""

from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """Report whether the application can serve traffic.

    Checks the database connection rather than returning a static ``ok``: a
    process that is running but cannot reach Postgres is not healthy, and an
    orchestrator needs to know the difference.
    """
    try:
        connection.ensure_connection()
    except Exception:  # noqa: BLE001 - any failure means "not ready"
        return JsonResponse({"status": "unhealthy", "database": "unreachable"}, status=503)

    return JsonResponse({"status": "ok", "database": "ok"})
