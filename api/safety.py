from django.http import JsonResponse

from api.utils import parse_date


def error_response(message, code, status=400, details=None):
    data = {"error": message, "code": code}
    if details:
        data["details"] = details
    return JsonResponse(data, status=status)


def require_staff_token(request):
    if request.user.is_staff or request.user.is_superuser:
        return None
    return error_response(
        "Staff token required",
        "staff_token_required",
        status=403,
    )


def ensure_closed_for_delete(instance, closed_state, noun):
    if instance.state != closed_state:
        return error_response(
            f"Only closed {noun}s can be deleted",
            f"{noun}_not_closed",
            details={"state": instance.state},
        )
    return None


def ensure_no_related_records_for_delete(queryset, related_name, noun):
    count = queryset.count()
    if count > 0:
        return error_response(
            f"Cannot delete {noun} with existing {related_name}",
            f"{noun}_has_{related_name}",
            details={f"{related_name}_count": count},
        )
    return None


def delete_object_or_error(
    instance, *, closed_state, related_queryset, related_name, noun
):
    """Delete instance if it's closed and has no related records.

    Returns the success JsonResponse, or an error response if a guard fails.
    """
    err = ensure_closed_for_delete(instance, closed_state, noun)
    if err:
        return err

    err = ensure_no_related_records_for_delete(
        related_queryset, related_name, noun
    )
    if err:
        return err

    instance.delete()
    return JsonResponse({"deleted": True})


def apply_patch_fields(
    instance,
    data,
    *,
    allowed_fields,
    valid_states,
    invalid_state_code,
    date_fields,
):
    """Apply a PATCH payload field-by-field with validation.

    Rejects unknown fields, validates ``state`` against ``valid_states`` and
    parses ``date_fields``. Returns an error response on the first invalid
    field, else None (mutating ``instance`` in place).
    """
    for field, value in data.items():
        error = validate_patch_field(
            field,
            value,
            allowed_fields=allowed_fields,
            valid_states=valid_states,
            invalid_state_code=invalid_state_code,
        )
        if error:
            return error

        value, error = parse_patch_field_value(
            field,
            value,
            date_fields=date_fields,
        )
        if error:
            return error

        setattr(instance, field, value)

    return None


def validate_patch_field(
    field,
    value,
    *,
    allowed_fields,
    valid_states,
    invalid_state_code,
):
    if field not in allowed_fields:
        return error_response(
            f"Cannot update field: {field}",
            "invalid_field",
            details={"field": field},
        )

    if field == "state" and value not in valid_states:
        return error_response(
            f"Invalid state. Must be one of: {sorted(valid_states)}",
            invalid_state_code,
            details={"valid_states": sorted(valid_states)},
        )

    return None


def parse_patch_field_value(field, value, *, date_fields):
    if field not in date_fields:
        return value, None

    parsed_value = parse_date(value)
    if parsed_value is None:
        return None, error_response(
            f"Invalid date format for {field}",
            "invalid_date_format",
            details={"field": field},
        )

    return parsed_value, None
