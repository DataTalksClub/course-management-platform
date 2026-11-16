from api.safety import error_response
from api.utils import parse_json_body
from courses.registration_email_change import (
    EmailChangeError,
    change_registration_email,
)

from .registration_campaign_serializers import registration_to_dict

BODY_FIELDS = {"email", "update_user", "dry_run"}


def change_registration_email_payload(registration, request):
    data, err = parse_json_body(request)
    if err:
        return None, err
    if not isinstance(data, dict):
        return None, error_response("Body must be an object", "invalid_body")
    unknown = set(data) - BODY_FIELDS
    if unknown:
        return None, error_response(
            f"Unknown field: {sorted(unknown)[0]}", "validation_error",
        )
    try:
        result = change_registration_email(
            registration,
            data.get("email"),
            update_user=bool(data.get("update_user", True)),
            apply=not bool(data.get("dry_run", False)),
        )
    except EmailChangeError as exc:
        return None, error_response(exc.message, exc.code, status=exc.status)
    payload = {
        "applied": result.applied,
        "old_email": result.old_email,
        "new_email": result.new_email,
        "user_id": result.user_id,
        "user_action": result.user_action,
        "enrollment_id": result.enrollment_id,
        "enrollment_created": result.enrollment_created,
        "emails_queued": 0,
        "registration": registration_to_dict(result.registration),
    }
    return payload, None
