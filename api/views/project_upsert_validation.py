from api.safety import error_response
from api.utils import instructions_url_error, parse_date
from api.views.project_upsert_rules import (
    PROJECT_UPSERT_REQUIRED_DATES,
    VALID_PROJECT_STATES,
)


def project_upsert_title(data):
    name = data.get("name")
    return data.get("title", name)


def project_upsert_missing_create_fields(data):
    title = project_upsert_title(data)
    missing_dates = []
    for field in PROJECT_UPSERT_REQUIRED_DATES:
        if not data.get(field):
            missing_dates.append(field)
    missing_title = not title
    has_missing_dates = bool(missing_dates)
    if missing_title:
        return True
    return has_missing_dates


def project_upsert_instructions_error(data):
    if "instructions_url" not in data:
        return None

    instructions_url = data.get("instructions_url")
    error = instructions_url_error(instructions_url)
    if not error:
        return None

    return error_response(
        error,
        "invalid_instructions_url",
        details={"field": "instructions_url"},
    )


def project_upsert_date_error(data):
    for field in PROJECT_UPSERT_REQUIRED_DATES:
        if field in data and parse_date(data[field]) is None:
            return error_response(
                f"Invalid date format for {field}",
                "invalid_date_format",
                details={"field": field},
            )
    return None


def project_upsert_state_error(data):
    if "state" not in data or data["state"] in VALID_PROJECT_STATES:
        return None

    valid_states = sorted(VALID_PROJECT_STATES)
    return error_response(
        f"Invalid state. Must be one of: {valid_states}",
        "invalid_project_state",
        details={"valid_states": valid_states},
    )


def project_upsert_validation_error(data, created):
    if created and project_upsert_missing_create_fields(data):
        return error_response(
            "title/name, submission_due_date, and peer_review_due_date are required",
            "missing_required_fields",
        )

    instructions_error = project_upsert_instructions_error(data)
    if instructions_error:
        return instructions_error

    date_error = project_upsert_date_error(data)
    if date_error:
        return date_error

    state_error = project_upsert_state_error(data)
    if state_error:
        return state_error

    return None
