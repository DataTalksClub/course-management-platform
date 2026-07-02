from dataclasses import dataclass

from api.safety import error_response
from api.utils import parse_date
from api.views.homework_upsert_common import (
    VALID_HOMEWORK_STATES,
    homework_title_from_data,
    invalid_due_date_response,
    invalid_homework_state_response,
    validate_homework_instructions_url_value,
)
from api.views.homework_upsert_questions import (
    homework_questions_replace_error,
)
from courses.models.homework import Homework


@dataclass(frozen=True)
class HomeworkUpsertValidationData:
    data: dict
    homework: Homework | None
    created: bool


def validate_homework_upsert(data, homework, created):
    validation_data = HomeworkUpsertValidationData(
        data=data,
        homework=homework,
        created=created,
    )
    for validator in (
        validate_created_homework_fields,
        validate_homework_instructions_url,
        validate_homework_due_date,
        validate_homework_state,
        validate_homework_questions,
    ):
        error = validator(validation_data)
        if error:
            return error

    return None


def validate_created_homework_fields(validation_data):
    title = homework_title_from_data(validation_data.data)
    due_date = validation_data.data.get("due_date")
    if validation_data.created and (not title or not due_date):
        return error_response(
            "title/name and due_date are required",
            "missing_required_fields",
        )
    return None


def validate_homework_instructions_url(validation_data):
    if "instructions_url" not in validation_data.data:
        return None

    instructions_url = validation_data.data.get("instructions_url")
    return validate_homework_instructions_url_value(instructions_url)


def validate_homework_due_date(validation_data):
    if "due_date" not in validation_data.data:
        return None

    due_date = parse_date(validation_data.data["due_date"])
    if due_date is None:
        return invalid_due_date_response()
    return None


def validate_homework_state(validation_data):
    data = validation_data.data
    if "state" in data and data["state"] not in VALID_HOMEWORK_STATES:
        return invalid_homework_state_response()
    return None


def validate_homework_questions(validation_data):
    if (
        validation_data.homework is None
        or "questions" not in validation_data.data
    ):
        return None
    error = homework_questions_replace_error(validation_data.homework)
    return error
