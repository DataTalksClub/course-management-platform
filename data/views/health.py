"""
Health check endpoint.

Provides a simple health check that returns the current application version.
"""

from django.conf import settings
from django.http import JsonResponse


def health_view(request):
    """
    Health check endpoint that returns the current version.

    Returns:
        JSON response with version information.
    """
    return JsonResponse({
        "status": "ok",
        "version": getattr(settings, "VERSION", "unknown"),
    })
