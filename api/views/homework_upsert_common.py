from dataclasses import dataclass

from api.safety import error_response
from api.utils import instructions_url_error
from courses.models import Course, Homework
from courses.models.homework import HomeworkState


@dataclass(frozen=True)
class HomeworkUpsertData:
    course: Course
    homework_slug: str
    data: dict
    homework: Homework | None
    created: bool


VALID_HOMEWORK_STATES = set()
for homework_state in HomeworkState:
    VALID_HOMEWORK_STATES.add(homework_state.value)

HOMEWORK_DIRECT_UPDATE_FIELDS = (
    "learning_in_public_cap",
    "homework_url_field",
    "time_spent_lectures_field",
    "time_spent_homework_field",
    "faq_contribution_field",
)


def homework_title_from_data(data):
    name = data.get("name")
    return data.get("title", name)


def invalid_instructions_url_response(error):
    return error_response(
        error,
        "invalid_instructions_url",
        details={"field": "instructions_url"},
    )


def invalid_due_date_response():
    return error_response(
        "Invalid date format for due_date",
        "invalid_date_format",
        details={"field": "due_date"},
    )


def invalid_homework_state_response():
    valid_states = sorted(VALID_HOMEWORK_STATES)
    return error_response(
        f"Invalid state. Must be one of: {valid_states}",
        "invalid_homework_state",
        details={"valid_states": valid_states},
    )


def validate_homework_instructions_url_value(instructions_url):
    error = instructions_url_error(instructions_url)
    if error:
        return invalid_instructions_url_response(error)
    return None
