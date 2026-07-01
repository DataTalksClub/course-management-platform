from dataclasses import dataclass

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from courses.models import Course, Homework
from courses.models.homework import HomeworkState
from courses.scoring import (
    HomeworkScoringStatus,
    score_homework_submissions,
)

from api.crud import (
    DeleteResponseConfig,
    DetailResponseConfig,
    PatchResponseConfig,
    detail_response,
    get_course_child_or_404,
)
from api.safety import (
    PatchFieldRules,
    error_response,
    require_staff_token,
)
from api.utils import (
    instructions_url_error,
    parse_date,
    parse_json_body,
    require_methods,
)
from api.views.homework_create import (
    create_question,
    homeworks_create_response,
    homeworks_list_response,
)
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


def _homework_score_response(homework):
    status, message = score_homework_submissions(homework.id)
    homework.refresh_from_db()
    submissions_count = homework.submission_set.count()
    if status == HomeworkScoringStatus.OK:
        response_status = 200
    else:
        response_status = 400

    if status == HomeworkScoringStatus.OK:
        rescored_submissions_count = submissions_count
    else:
        rescored_submissions_count = 0

    payload = {
        "status": status.name,
        "message": message,
        "homework_id": homework.id,
        "homework_slug": homework.slug,
        "state": homework.state,
        "submissions_count": submissions_count,
        "rescored_submissions_count": rescored_submissions_count,
    }
    response = JsonResponse(payload, status=response_status)
    return response


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def homeworks_view(request, course_slug):
    """
    GET /api/courses/<slug>/homeworks/ - List homeworks.
    POST /api/courses/<slug>/homeworks/ - Create homework(s), bulk supported.
    """
    course = get_object_or_404(Course, slug=course_slug)

    if request.method == "GET":
        return homeworks_list_response(course)

    return homeworks_create_response(request, course)


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


def _homework_title_from_data(data):
    name = data.get("name")
    return data.get("title", name)


def _invalid_instructions_url_response(error):
    return error_response(
        error,
        "invalid_instructions_url",
        details={"field": "instructions_url"},
    )


def _invalid_due_date_response():
    return error_response(
        "Invalid date format for due_date",
        "invalid_date_format",
        details={"field": "due_date"},
    )


def _invalid_homework_state_response():
    valid_states = sorted(VALID_HOMEWORK_STATES)
    return error_response(
        f"Invalid state. Must be one of: {valid_states}",
        "invalid_homework_state",
        details={"valid_states": valid_states},
    )


def _apply_homework_text_fields(homework, data):
    title = _homework_title_from_data(data)
    if title is not None:
        homework.title = title

    if "description" in data:
        homework.description = data["description"]


def _apply_homework_validated_fields(homework, data):
    field_applicators = (
        _apply_homework_instructions_url,
        _apply_homework_due_date,
        _apply_homework_state,
    )
    for apply_field in field_applicators:
        error = apply_field(homework, data)
        if error:
            return error

    return None


def _apply_homework_data(homework, data):
    _apply_homework_text_fields(homework, data)

    error = _apply_homework_validated_fields(homework, data)
    if error:
        return error

    _apply_homework_direct_fields(homework, data)
    return None


def _apply_homework_instructions_url(homework, data):
    if "instructions_url" not in data:
        return None

    error = instructions_url_error(data["instructions_url"])
    if error:
        return _invalid_instructions_url_response(error)

    homework.instructions_url = data["instructions_url"]
    return None


def _apply_homework_due_date(homework, data):
    if "due_date" not in data:
        return None

    due_date = parse_date(data["due_date"])
    if due_date is None:
        return _invalid_due_date_response()

    homework.due_date = due_date
    return None


def _apply_homework_state(homework, data):
    if "state" not in data:
        return None

    if data["state"] not in VALID_HOMEWORK_STATES:
        return _invalid_homework_state_response()

    homework.state = data["state"]
    return None


def _apply_homework_direct_fields(homework, data):
    for field in HOMEWORK_DIRECT_UPDATE_FIELDS:
        if field not in data:
            continue
        setattr(homework, field, data[field])


def _homework_questions_replace_error(homework):
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


def _replace_homework_questions(homework, questions_data):
    error = _homework_questions_replace_error(homework)
    if error:
        return error

    homework.question_set.all().delete()
    for q_data in questions_data:
        create_question(homework, q_data)
    return None


def _validate_homework_upsert(data, homework, created):
    """Validate an upsert payload. Returns an error response, or None if ok."""
    validation_data = HomeworkUpsertValidationData(
        data=data,
        homework=homework,
        created=created,
    )
    validators = (
        _validate_created_homework_fields,
        _validate_homework_instructions_url,
        _validate_homework_due_date,
        _validate_homework_state,
        _validate_homework_questions,
    )
    for validator in validators:
        error = validator(validation_data)
        if error:
            return error

    return None


def _validate_created_homework_fields(validation_data):
    title = _homework_title_from_data(validation_data.data)
    due_date = validation_data.data.get("due_date")
    if validation_data.created and (not title or not due_date):
        return error_response(
            "title/name and due_date are required",
            "missing_required_fields",
        )
    return None


def _validate_homework_instructions_url(validation_data):
    if "instructions_url" not in validation_data.data:
        return None

    instructions_url = validation_data.data.get("instructions_url")
    error = instructions_url_error(instructions_url)
    if error:
        return _invalid_instructions_url_response(error)

    return None


def _validate_homework_due_date(validation_data):
    if "due_date" not in validation_data.data:
        return None

    due_date = parse_date(validation_data.data["due_date"])
    if due_date is None:
        return _invalid_due_date_response()
    return None


def _validate_homework_state(validation_data):
    data = validation_data.data
    if "state" in data and data["state"] not in VALID_HOMEWORK_STATES:
        return _invalid_homework_state_response()
    return None


def _validate_homework_questions(validation_data):
    if (
        validation_data.homework is None
        or "questions" not in validation_data.data
    ):
        return None
    error = _homework_questions_replace_error(validation_data.homework)
    return error


def _homework_by_slug(course, homework_slug):
    return Homework.objects.filter(
        course=course,
        slug=homework_slug,
    ).first()


def _create_homework_for_upsert(upsert):
    title = _homework_title_from_data(upsert.data)
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


def _replace_homework_questions_if_present(homework, data):
    if "questions" not in data:
        return None
    return _replace_homework_questions(homework, data["questions"])


def _save_homework_upsert(upsert):
    homework = upsert.homework
    with transaction.atomic():
        if upsert.created:
            homework = _create_homework_for_upsert(upsert)

        error = _apply_homework_data(homework, upsert.data)
        if error:
            return homework, error

        homework.save()

        error = _replace_homework_questions_if_present(
            homework,
            upsert.data,
        )
        if error:
            return homework, error

    return homework, None


def _homework_upsert_data(course, homework_slug, data):
    homework = _homework_by_slug(course, homework_slug)
    created = homework is None

    error = _validate_homework_upsert(data, homework, created)
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


def _saved_homework_upsert(course, homework_slug, data):
    upsert, error = _homework_upsert_data(course, homework_slug, data)
    if error:
        return None, error

    homework, error = _save_homework_upsert(upsert)
    if error:
        return None, error

    save_result = (upsert, homework)
    return save_result, None


def _upsert_homework_by_slug(request, course_slug, homework_slug):
    course = get_object_or_404(Course, slug=course_slug)
    data, err = parse_json_body(request)
    if err:
        return err

    save_result, error = _saved_homework_upsert(
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


def _homework_detail_config(homework):
    return DetailResponseConfig(
        patch=PatchResponseConfig(
            to_dict=homework_to_dict,
            rules=HOMEWORK_PATCH_RULES,
        ),
        delete=DeleteResponseConfig(
            closed_state=HomeworkState.CLOSED.value,
            related_queryset=homework.submission_set.all(),
            related_name="submissions",
            noun="homework",
        ),
    )


def _homework_detail_response(
    request,
    course_slug,
    *,
    homework_id=None,
    homework_slug=None,
):
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_course_child_or_404(
        Homework,
        course,
        object_id=homework_id,
        slug=homework_slug,
    )
    config = _homework_detail_config(homework)
    return detail_response(
        request,
        homework,
        config,
    )


@token_required
@csrf_exempt
@require_methods("GET", "PATCH", "DELETE")
def homework_detail_view(request, course_slug, homework_id):
    """
    GET /api/courses/<slug>/homeworks/<id>/ - Homework detail.
    PATCH /api/courses/<slug>/homeworks/<id>/ - Update homework.
    DELETE /api/courses/<slug>/homeworks/<id>/ - Delete homework.
    """
    return _homework_detail_response(
        request, course_slug, homework_id=homework_id
    )


@token_required
@csrf_exempt
@require_methods("GET", "PUT", "PATCH", "DELETE")
def homework_detail_by_slug_view(request, course_slug, homework_slug):
    """
    GET /api/courses/<slug>/homeworks/by-slug/<slug>/ - Homework detail.
    PUT /api/courses/<slug>/homeworks/by-slug/<slug>/ - Upsert homework.
    PATCH /api/courses/<slug>/homeworks/by-slug/<slug>/ - Update homework.
    DELETE /api/courses/<slug>/homeworks/by-slug/<slug>/ - Delete homework.
    """
    if request.method == "PUT":
        staff_error = require_staff_token(request)
        if staff_error:
            return staff_error

        return _upsert_homework_by_slug(
            request, course_slug, homework_slug
        )

    return _homework_detail_response(
        request, course_slug, homework_slug=homework_slug
    )


@token_required
@csrf_exempt
@require_methods("POST")
def homework_score_view(request, course_slug, homework_id):
    """
    POST /api/courses/<slug>/homeworks/<id>/score/ - Score homework.
    """
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    homework = get_course_child_or_404(
        Homework,
        course,
        object_id=homework_id,
    )
    return _homework_score_response(homework)


@token_required
@csrf_exempt
@require_methods("POST")
def homework_score_by_slug_view(request, course_slug, homework_slug):
    """
    POST /api/courses/<slug>/homeworks/by-slug/<slug>/score/ - Score homework.
    """
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    homework = get_course_child_or_404(
        Homework,
        course,
        slug=homework_slug,
    )
    return _homework_score_response(homework)
