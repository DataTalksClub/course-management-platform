"""
Health endpoints.

The live endpoint only reports that Django can answer requests. The detailed
endpoint reports Relay configuration problems as degraded service status.
"""

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from course_management.datamailer.client import (
    RELAY_CONFIG_MISSING,
    get_relay_health_status,
    is_production,
)


@require_GET
def live_health_view(request):
    """Return process liveness without depending on Relay or the database."""
    return JsonResponse({"status": "ok", "version": settings.VERSION})


@require_GET
def health_view(request):
    """
    Health check endpoint that returns the current version and service status.

    Returns:
        JSON response with version and status information.
    """
    relay_health = get_relay_health_status()
    is_prod = is_production()
    is_healthy = relay_health["status"] == "ok"

    if (
        not is_healthy
        and not is_prod
        and relay_health.get("error") == RELAY_CONFIG_MISSING
    ):
        is_healthy = True
        relay_status = "unconfigured"
    else:
        relay_status = relay_health.get("relay_status", relay_health["status"])

    payload = {
        "status": "ok",
        "version": settings.VERSION,
        "relay_status": relay_status,
    }

    if not is_healthy:
        payload["degraded"] = True
        payload["relay_error"] = relay_health["error"]
        payload["relay"] = {
            "status": "FAIL",
            "error": relay_health["error"],
            "degraded": True,
            "dry_run": relay_health.get("dry_run", False),
            "dry_run_prod": relay_health.get("dry_run_on_prod", False),
        }
        if relay_health.get("dry_run_on_prod"):
            payload["dry_run_prod"] = True
            payload["RELAY_TRANSACTIONAL_DRY_RUN"] = "FAIL"
    else:
        payload["relay"] = {
            "status": "ok",
        }

    return JsonResponse(payload)
