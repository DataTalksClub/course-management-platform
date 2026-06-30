import json
from datetime import datetime
from functools import wraps

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.http import JsonResponse

INSTRUCTIONS_URL_VALIDATOR = URLValidator(schemes=["http", "https"])


def instructions_url_error(value):
    """Return an error message if value is a non-empty, non-http(s) URL."""
    if not value:
        return None
    try:
        INSTRUCTIONS_URL_VALIDATOR(value)
    except ValidationError:
        return "instructions_url must be a valid http(s) URL"
    return None


def parse_date(date_str):
    """Parse an ISO 8601 date string, returning a datetime or None."""
    try:
        normalized_date_str = date_str.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized_date_str)
    except (ValueError, AttributeError):
        return None


def parse_json_body(request):
    """Parse JSON body from request, returning (data, error_response)."""
    try:
        data = json.loads(request.body)
        return data, None
    except (json.JSONDecodeError, ValueError):
        error_payload = {"error": "Invalid JSON"}
        error_response = JsonResponse(error_payload, status=400)
        return None, error_response


def require_methods(*methods):
    """Decorator to restrict allowed HTTP methods."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                error_payload = {"error": "Method not allowed"}
                response = JsonResponse(error_payload, status=405)
                return response
            return view_func(request, *args, **kwargs)
        wrapper.api_methods = methods
        return wrapper
    return decorator
