"""API Layer - versioned JSON endpoints under /api/v1/ (see API Standards)."""

from django.http import JsonResponse


def api_root(request):
    """Service descriptor so clients can discover available resources."""
    return JsonResponse(
        {
            "service": "smartpark-api",
            "version": "v1",
            "resources": [
                "/api/v1/slots",
                "/api/v1/vehicles",
                "/api/v1/sessions",
                "/api/v1/payments",
            ],
            "status": "ok",
        }
    )
