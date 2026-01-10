"""
Health check endpoint.

Provides a simple health check that returns the current application version.
"""

from django.http import JsonResponse


def health_view(request):
    """
    Health check endpoint that returns the current version.

    Returns:
        JSON response with version information.
    """
    return JsonResponse({
        "status": "ok",
        "version": "0.1.0",
    })
