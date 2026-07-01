from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from api.crud import PatchResponseConfig
from api.safety import PatchFieldRules, require_staff_token
from api.utils import parse_json_body
from api.views.homework_serializers import homework_to_dict
from api.views.homework_upsert_common import (
    HomeworkUpsertData,
    VALID_HOMEWORK_STATES,
)
from api.views.homework_upsert_save import (
    homework_by_slug,
    save_homework_upsert,
)
from api.views.homework_upsert_validation import validate_homework_upsert
from courses.models.course import Course


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

HOMEWORK_PATCH_RULES = PatchFieldRules(
    HOMEWORK_PATCH_FIELDS,
    VALID_HOMEWORK_STATES,
    "invalid_homework_state",
    {"due_date"},
)

HOMEWORK_PATCH_CONFIG = PatchResponseConfig(
    to_dict=homework_to_dict,
    rules=HOMEWORK_PATCH_RULES,
)


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
