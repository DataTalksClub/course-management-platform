import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from accounts.services.timezones import get_timezone_label, is_valid_timezone


def _parse_timezone_request(request):
    try:
        data = json.loads(request.body)
        return data, None
    except (json.JSONDecodeError, ValueError):
        return None, "Invalid JSON"


def _timezone_field_value(data):
    timezone_name = data.get("timezone")
    if timezone_name is None:
        return None, "timezone field is required"
    return timezone_name, None


def _validated_timezone_value(timezone_value):
    if not isinstance(timezone_value, str):
        return None, "timezone must be a string"

    timezone_name = timezone_value.strip()
    error = _timezone_name_error(timezone_name)
    if error:
        return None, error

    return timezone_name, None


def _timezone_name_error(timezone_name):
    if timezone_name and not is_valid_timezone(timezone_name):
        return "Invalid timezone"
    return None


def _validated_timezone_name(data):
    timezone_value, error = _timezone_field_value(data)
    if error:
        return None, error

    timezone_name, error = _validated_timezone_value(timezone_value)
    return timezone_name, error


def _timezone_preference_response(timezone_name):
    timezone_label = get_timezone_label(timezone_name)
    response = JsonResponse(
        {
            "status": "ok",
            "timezone": timezone_name,
            "label": timezone_label,
        }
    )
    return response


@login_required
@require_POST
def update_timezone_preference(request):
    data, error = _parse_timezone_request(request)
    if error:
        payload = {"error": error}
        response = JsonResponse(payload, status=400)
        return response

    timezone_name, error = _validated_timezone_name(data)
    if error:
        payload = {"error": error}
        response = JsonResponse(payload, status=400)
        return response

    user = request.user
    passive_update = data.get("passive")
    saved_timezone = user.preferred_timezone
    if passive_update and saved_timezone:
        return _timezone_preference_response(saved_timezone)

    user.preferred_timezone = timezone_name
    user.save(update_fields=["preferred_timezone"])
    return _timezone_preference_response(user.preferred_timezone)
