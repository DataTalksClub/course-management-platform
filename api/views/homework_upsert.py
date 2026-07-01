from dataclasses import dataclass

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from courses.models import Course, Homework
from courses.models.homework import HomeworkState

from api.crud import PatchResponseConfig
from api.safety import PatchFieldRules, error_response, require_staff_token
from api.utils import instructions_url_error, parse_date, parse_json_body
from api.views.homework_create import create_question
from api.views.homework_serializers import (
    homework_delete_blockers,
    homework_to_dict,
)


@dataclass(frozen=True)
class HomeworkUpsertData:
    course: Course
    homework_slug: str
    data: dict
    homework: Homework | None
    created: bool


@dataclass(frozen=True)
class HomeworkUpsertValidationData:
    data: dict
    homework: Homework | None
    created: bool


HOMEWORK_PATCH_FIELDS = {
    "title",
    "description",
    "due_date",
    "state",
    "instructions_url",
    "learning_in_public_cap",
    "homework_url_field",
    "time_spent_lectures_field",
    "time_spent_homework_field",
    "faq_contribution_field",
}

VALID_HOMEWORK_STATES = set()
for homework_state in HomeworkState:
    VALID_HOMEWORK_STATES.add(homework_state.value)

HOMEWORK_PATCH_RULES = PatchFieldRules(
    HOMEWORK_PATCH_FIELDS,
    VALID_HOMEWORK_STATES,
    "invalid_homework_state",
    {"due_date"},
)

HOMEWORK_DIRECT_UPDATE_FIELDS = (
    "learning_in_public_cap",
    "homework_url_field",
    "time_spent_lectures_field",
    "time_spent_homework_field",
    "faq_contribution_field",
)

HOMEWORK_PATCH_CONFIG = PatchResponseConfig(
    to_dict=homework_to_dict,
    rules=HOMEWORK_PATCH_RULES,
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


def apply_homework_data(homework, data):
    apply_homework_text_fields(homework, data)

    error = apply_homework_validated_fields(homework, data)
    if error:
        return error

    apply_homework_direct_fields(homework, data)
    return None


def apply_homework_instructions_url(homework, data):
    if "instructions_url" not in data:
        return None

    error = instructions_url_error(data["instructions_url"])
    if error:
        return invalid_instructions_url_response(error)

    homework.instructions_url = data["instructions_url"]
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


def homework_questions_replace_error(homework):
    if homework_delete_blockers(homework):
        return error_response(
            "Questions can only be replaced for closed homeworks with no submissions",
            "homework_questions_replace_blocked",
            details={
                "delete_blockers": homework_delete_blockers(homework)
            },
        )

    answered_questions = homework.question_set.filter(
        answer__isnull=False
    ).distinct()
    if answered_questions.exists():
        return error_response(
            "Cannot replace questions with existing answers",
            "homework_questions_have_answers",
            details={
                "answered_questions_count": answered_questions.count()
            },
        )

    return None


def replace_homework_questions(homework, questions_data):
    error = homework_questions_replace_error(homework)
    if error:
        return error

    homework.question_set.all().delete()
    for question_data in questions_data:
        create_question(homework, question_data)
    return None


def validate_homework_upsert(data, homework, created):
    validation_data = HomeworkUpsertValidationData(
        data=data,
        homework=homework,
        created=created,
    )
    validators = (
        validate_created_homework_fields,
        validate_homework_instructions_url,
        validate_homework_due_date,
        validate_homework_state,
        validate_homework_questions,
    )
    for validator in validators:
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
    error = instructions_url_error(instructions_url)
    if error:
        return invalid_instructions_url_response(error)

    return None


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


def homework_by_slug(course, homework_slug):
    return Homework.objects.filter(
        course=course,
        slug=homework_slug,
    ).first()


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


def replace_homework_questions_if_present(homework, data):
    if "questions" not in data:
        return None
    return replace_homework_questions(homework, data["questions"])


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


def homework_upsert_data(course, homework_slug, data):
    homework = homework_by_slug(course, homework_slug)
    created = homework is None

    error = validate_homework_upsert(data, homework, created)
    if error:
        return None, error

    upsert = HomeworkUpsertData(
        course=course,
        homework_slug=homework_slug,
        data=data,
        homework=homework,
        created=created,
    )
    return upsert, None


def saved_homework_upsert(course, homework_slug, data):
    upsert, error = homework_upsert_data(course, homework_slug, data)
    if error:
        return None, error

    homework, error = save_homework_upsert(upsert)
    if error:
        return None, error

    save_result = (upsert, homework)
    return save_result, None


def upsert_homework_by_slug(request, course_slug, homework_slug):
    course = get_object_or_404(Course, slug=course_slug)
    data, err = parse_json_body(request)
    if err:
        return err

    save_result, error = saved_homework_upsert(
        course, homework_slug, data
    )
    if error:
        return error

    upsert, homework = save_result

    homework_data = homework_to_dict(homework)
    if upsert.created:
        response_status = 201
    else:
        response_status = 200
    response = JsonResponse(homework_data, status=response_status)
    return response


def staff_upsert_homework_by_slug(request, course_slug, homework_slug):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    return upsert_homework_by_slug(request, course_slug, homework_slug)
