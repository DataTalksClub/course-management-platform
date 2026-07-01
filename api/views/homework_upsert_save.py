from django.db import transaction

from api.utils import parse_date
from api.views.homework_upsert_common import (
    HOMEWORK_DIRECT_UPDATE_FIELDS,
    VALID_HOMEWORK_STATES,
    homework_title_from_data,
    invalid_due_date_response,
    invalid_homework_state_response,
    validate_homework_instructions_url_value,
)
from api.views.homework_upsert_questions import replace_homework_questions
from courses.models import Homework
from courses.models.homework import HomeworkState


def homework_by_slug(course, homework_slug):
    return Homework.objects.filter(
        course=course,
        slug=homework_slug,
    ).first()


def save_homework_upsert(upsert):
    homework = upsert.homework
    with transaction.atomic():
        if upsert.created:
            homework = create_homework_for_upsert(upsert)

        error = apply_homework_data(homework, upsert.data)
        if error:
            return homework, error

        homework.save()

        error = replace_homework_questions_if_present(
            homework,
            upsert.data,
        )
        if error:
            return homework, error

    return homework, None


def create_homework_for_upsert(upsert):
    title = homework_title_from_data(upsert.data)
    description = upsert.data.get("description", "")
    instructions_url = upsert.data.get("instructions_url")
    due_date = parse_date(upsert.data["due_date"])

    return Homework.objects.create(
        course=upsert.course,
        slug=upsert.homework_slug,
        title=title,
        description=description,
        instructions_url=instructions_url,
        due_date=due_date,
        state=HomeworkState.CLOSED.value,
    )


def apply_homework_data(homework, data):
    apply_homework_text_fields(homework, data)

    error = apply_homework_validated_fields(homework, data)
    if error:
        return error

    apply_homework_direct_fields(homework, data)
    return None


def apply_homework_text_fields(homework, data):
    title = homework_title_from_data(data)
    if title is not None:
        homework.title = title

    if "description" in data:
        homework.description = data["description"]


def apply_homework_validated_fields(homework, data):
    field_applicators = (
        apply_homework_instructions_url,
        apply_homework_due_date,
        apply_homework_state,
    )
    for apply_field in field_applicators:
        error = apply_field(homework, data)
        if error:
            return error

    return None


def apply_homework_instructions_url(homework, data):
    if "instructions_url" not in data:
        return None

    instructions_url = data["instructions_url"]
    error = validate_homework_instructions_url_value(instructions_url)
    if error:
        return error

    homework.instructions_url = instructions_url
    return None


def apply_homework_due_date(homework, data):
    if "due_date" not in data:
        return None

    due_date = parse_date(data["due_date"])
    if due_date is None:
        return invalid_due_date_response()

    homework.due_date = due_date
    return None


def apply_homework_state(homework, data):
    if "state" not in data:
        return None

    if data["state"] not in VALID_HOMEWORK_STATES:
        return invalid_homework_state_response()

    homework.state = data["state"]
    return None


def apply_homework_direct_fields(homework, data):
    for field in HOMEWORK_DIRECT_UPDATE_FIELDS:
        if field not in data:
            continue
        setattr(homework, field, data[field])


def replace_homework_questions_if_present(homework, data):
    if "questions" not in data:
        return None
    return replace_homework_questions(homework, data["questions"])
