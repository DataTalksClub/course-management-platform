"""
Health check endpoint.

Provides a simple health check that returns the current application version.
"""

import os
import tomllib
from pathlib import Path

from django.http import JsonResponse


def get_version():
    """Read version from pyproject.toml."""
    pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data.get("project", {}).get("version", "unknown")
    except Exception:
        return "unknown"


def health_view(request):
    """
    Health check endpoint that returns the current version.

    Returns:
        JSON response with version information.
    """
    return JsonResponse({
        "status": "ok",
        "version": get_version(),
    })
