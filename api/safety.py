from dataclasses import dataclass

from django.http import JsonResponse

from api.utils import parse_date


@dataclass(frozen=True)
class PatchFieldRules:
    allowed_fields: set[str]
    valid_states: set[str]
    invalid_state_code: str
    date_fields: set[str]


@dataclass(frozen=True)
class DeleteObjectData:
    instance: object
    closed_state: str
    related_queryset: object
    related_name: str
    noun: str


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


def delete_object_or_error(data):
    """Delete instance if it's closed and has no related records.

    Returns the success JsonResponse, or an error response if a guard fails.
    """
    err = ensure_closed_for_delete(
        data.instance,
        data.closed_state,
        data.noun,
    )
    if err:
        return err

    err = ensure_no_related_records_for_delete(
        data.related_queryset,
        data.related_name,
        data.noun,
    )
    if err:
        return err

    data.instance.delete()
    payload = {"deleted": True}
    return JsonResponse(payload)


def apply_patch_fields(
    instance,
    data,
    rules,
):
    """Apply a PATCH payload field-by-field with validation.

    Rejects unknown fields, validates ``state`` against ``valid_states`` and
    parses ``date_fields``. Returns an error response on the first invalid
    field, else None (mutating ``instance`` in place).
    """
    for field, value in data.items():
        error = apply_patch_field(instance, field, value, rules)
        if error:
            return error

    return None


def apply_patch_field(instance, field, value, rules):
    error = validate_patch_field(field, value, rules)
    if error:
        return error

    parsed_value, error = parse_patch_field_value(field, value, rules)
    if error:
        return error

    setattr(instance, field, parsed_value)
    return None


def validate_patch_field(
    field,
    value,
    rules,
):
    if field not in rules.allowed_fields:
        return error_response(
            f"Cannot update field: {field}",
            "invalid_field",
            details={"field": field},
        )

    if field == "state" and value not in rules.valid_states:
        valid_states = sorted(rules.valid_states)
        return error_response(
            f"Invalid state. Must be one of: {valid_states}",
            rules.invalid_state_code,
            details={"valid_states": valid_states},
        )

    return None


def parse_patch_field_value(field, value, rules):
    if field not in rules.date_fields:
        return value, None

    parsed_value = parse_date(value)
    if parsed_value is None:
        details = {"field": field}
        error = error_response(
            f"Invalid date format for {field}",
            "invalid_date_format",
            details=details,
        )
        return None, error

    return parsed_value, None
