from django.core.exceptions import ValidationError

from courses.models.start_time import (
    parse_start_time,
    validate_start_time,
)


def normalize_start_time(data):
    if "starts_at" in data:
        data["starts_at"] = parse_start_time(data["starts_at"])
    return data


def start_time_error(instance):
    from api.safety import error_response

    if not hasattr(instance, "starts_at"):
        return None
    try:
        validate_start_time(instance)
    except ValidationError as exc:
        return error_response(
            "Invalid start time",
            "validation_error",
            details=exc.message_dict,
        )
    return None


def apply_start_time(instance, data):
    try:
        if "starts_at" in data:
            instance.starts_at = parse_start_time(data["starts_at"])
        validate_start_time(instance)
    except ValidationError as exc:
        return exc.messages[0]
    return None
