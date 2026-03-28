import json
from datetime import datetime
from functools import wraps

from django.http import JsonResponse


def parse_date(date_str):
    """Parse an ISO 8601 date string, returning a datetime or None."""
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def parse_json_body(request):
    """Parse JSON body from request, returning (data, error_response)."""
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, ValueError):
        return None, JsonResponse({"error": "Invalid JSON"}, status=400)


def require_methods(*methods):
    """Decorator to restrict allowed HTTP methods."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return JsonResponse({"error": "Method not allowed"}, status=405)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
