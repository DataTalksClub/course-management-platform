from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.text import slugify

from accounts.auth import token_required
from courses.models import Course, Homework, Question
from courses.models.homework import HomeworkState
from courses.scoring import (
    HomeworkScoringStatus,
    score_homework_submissions,
)

from api.crud import (
    bulk_create_response,
    detail_response,
    get_course_child_or_404,
)
from api.safety import (
    error_response,
    require_staff_token,
)
from api.utils import (
    instructions_url_error,
    parse_date,
    parse_json_body,
    require_methods,
)


def _homework_delete_blockers(hw):
    blockers = []
    submissions_count = hw.submission_set.count()
    if hw.state != HomeworkState.CLOSED.value:
        blockers.append("not_closed")
    if submissions_count > 0:
        blockers.append("has_submissions")
    return blockers


def _homework_to_dict(hw):
    submissions_count = hw.submission_set.count()
    delete_blockers = _homework_delete_blockers(hw)
    return {
        "id": hw.id,
        "slug": hw.slug,
        "title": hw.title,
        "description": hw.description,
        "instructions_url": hw.instructions_url,
        "due_date": hw.due_date.isoformat(),
        "state": hw.state,
        "learning_in_public_cap": hw.learning_in_public_cap,
        "homework_url_field": hw.homework_url_field,
        "time_spent_lectures_field": hw.time_spent_lectures_field,
        "time_spent_homework_field": hw.time_spent_homework_field,
        "faq_contribution_field": hw.faq_contribution_field,
        "questions_count": hw.question_set.count(),
        "submissions_count": submissions_count,
        "can_delete": not delete_blockers,
        "delete_blockers": delete_blockers,
    }


def _homework_score_response(homework):
    status, message = score_homework_submissions(homework.id)
    homework.refresh_from_db()
    submissions_count = homework.submission_set.count()
    response_status = 200 if status == HomeworkScoringStatus.OK else 400
    return JsonResponse(
        {
            "status": status.name,
            "message": message,
            "homework_id": homework.id,
            "homework_slug": homework.slug,
            "state": homework.state,
            "submissions_count": submissions_count,
            "rescored_submissions_count": (
                submissions_count
                if status == HomeworkScoringStatus.OK
                else 0
            ),
        },
        status=response_status,
    )


def _homework_create_defaults(hw_data, name, due_date, instructions_url):
    return {
        "title": name,
        "description": hw_data.get("description", ""),
        "instructions_url": instructions_url,
        "due_date": due_date,
        "state": HomeworkState.CLOSED.value,
    }


def _create_questions(homework, questions_data):
    for q_data in questions_data:
        _create_question(homework, q_data)


def _homework_create_required_values(hw_data):
    name = hw_data.get("name")
    due_date_str = hw_data.get("due_date")

    if not name or not due_date_str:
        return None, None, "name and due_date are required"

    return name, due_date_str, None


def _homework_create_instructions_url(hw_data):
    instructions_url = hw_data.get("instructions_url")
    if instructions_url and (
        error := instructions_url_error(instructions_url)
    ):
        return None, error

    return instructions_url, None


def _homework_create_due_date(due_date_str):
    due_date = parse_date(due_date_str)
    if due_date is None:
        return None, f"Invalid date format: {due_date_str}"

    return due_date, None


def _homework_create_slug(course, hw_data, name):
    slug = hw_data.get("slug") or slugify(name)
    if Homework.objects.filter(course=course, slug=slug).exists():
        return None, f"Homework with slug '{slug}' already exists"

    return slug, None


def _homework_create_attrs(course, hw_data):
    name, due_date_str, error = _homework_create_required_values(hw_data)
    if error:
        return None, error

    instructions_url, error = _homework_create_instructions_url(hw_data)
    if error:
        return None, error

    due_date, error = _homework_create_due_date(due_date_str)
    if error:
        return None, error

    slug, error = _homework_create_slug(course, hw_data, name)
    if error:
        return None, error

    attrs = _homework_create_defaults(
        hw_data, name, due_date, instructions_url
    )
    attrs["slug"] = slug
    return attrs, None


def _create_homework(course, hw_data):
    """Create a homework. Returns (dict, None) or (None, error_str)."""
    attrs, error = _homework_create_attrs(course, hw_data)
    if error:
        return None, error

    homework = Homework.objects.create(
        course=course,
        **attrs,
    )

    _create_questions(homework, hw_data.get("questions", []))

    return _homework_to_dict(homework), None


def _create_question(homework, q_data):
    Question.objects.create(
        homework=homework,
        text=q_data.get("text", ""),
        question_type=q_data.get("question_type", "FF"),
        answer_type=q_data.get("answer_type"),
        possible_answers="\n".join(q_data.get("possible_answers", [])),
        correct_answer=q_data.get("correct_answer", ""),
        scores_for_correct_answer=q_data.get(
            "scores_for_correct_answer", 1
        ),
    )


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
        homeworks = Homework.objects.filter(course=course).order_by(
            "id"
        )
        return JsonResponse(
            {
                "homeworks": [
                    _homework_to_dict(hw) for hw in homeworks
                ],
            }
        )

    # POST
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    data, err = parse_json_body(request)
    if err:
        return err

    return bulk_create_response(
        data,
        lambda item: _create_homework(course, item),
    )


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

VALID_HOMEWORK_STATES = {s.value for s in HomeworkState}


HOMEWORK_DIRECT_UPDATE_FIELDS = (
    "learning_in_public_cap",
    "homework_url_field",
    "time_spent_lectures_field",
    "time_spent_homework_field",
    "faq_contribution_field",
)


def _homework_title_from_data(data):
    return data.get("title", data.get("name"))


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
    return error_response(
        f"Invalid state. Must be one of: {sorted(VALID_HOMEWORK_STATES)}",
        "invalid_homework_state",
        details={"valid_states": sorted(VALID_HOMEWORK_STATES)},
    )


def _apply_homework_text_fields(homework, data):
    title = _homework_title_from_data(data)
    if title is not None:
        homework.title = title

    if "description" in data:
        homework.description = data["description"]


def _apply_homework_validated_fields(homework, data):
    for apply_field in (
        _apply_homework_instructions_url,
        _apply_homework_due_date,
        _apply_homework_state,
    ):
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
    if _homework_delete_blockers(homework):
        return error_response(
            "Questions can only be replaced for closed homeworks with no submissions",
            "homework_questions_replace_blocked",
            details={
                "delete_blockers": _homework_delete_blockers(homework)
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
        _create_question(homework, q_data)
    return None


def _validate_homework_upsert(data, homework, created):
    """Validate an upsert payload. Returns an error response, or None if ok."""
    error = _validate_created_homework_fields(data, created)
    if error:
        return error

    error = _validate_homework_instructions_url(data)
    if error:
        return error

    error = _validate_homework_due_date(data)
    if error:
        return error

    error = _validate_homework_state(data)
    if error:
        return error

    return _validate_homework_questions(data, homework)


def _validate_created_homework_fields(data, created):
    title = _homework_title_from_data(data)
    if created and (not title or not data.get("due_date")):
        return error_response(
            "title/name and due_date are required",
            "missing_required_fields",
        )
    return None


def _validate_homework_instructions_url(data):
    if "instructions_url" not in data:
        return None

    error = instructions_url_error(data.get("instructions_url"))
    if error:
        return _invalid_instructions_url_response(error)

    return None


def _validate_homework_due_date(data):
    if "due_date" in data and parse_date(data["due_date"]) is None:
        return _invalid_due_date_response()
    return None


def _validate_homework_state(data):
    if "state" in data and data["state"] not in VALID_HOMEWORK_STATES:
        return _invalid_homework_state_response()
    return None


def _validate_homework_questions(data, homework):
    if homework is None or "questions" not in data:
        return None
    return _homework_questions_replace_error(homework)


def _homework_by_slug(course, homework_slug):
    return Homework.objects.filter(
        course=course,
        slug=homework_slug,
    ).first()


def _create_homework_for_upsert(course, homework_slug, data):
    title = _homework_title_from_data(data)
    return Homework.objects.create(
        course=course,
        slug=homework_slug,
        title=title,
        description=data.get("description", ""),
        instructions_url=data.get("instructions_url"),
        due_date=parse_date(data["due_date"]),
        state=HomeworkState.CLOSED.value,
    )


def _replace_homework_questions_if_present(homework, data):
    if "questions" not in data:
        return None
    return _replace_homework_questions(homework, data["questions"])


def _save_homework_upsert(course, homework_slug, data, homework, created):
    with transaction.atomic():
        if created:
            homework = _create_homework_for_upsert(
                course, homework_slug, data
            )

        error = _apply_homework_data(homework, data)
        if error:
            return homework, error

        homework.save()

        error = _replace_homework_questions_if_present(homework, data)
        if error:
            return homework, error

    return homework, None


def _upsert_homework_by_slug(request, course_slug, homework_slug):
    course = get_object_or_404(Course, slug=course_slug)
    data, err = parse_json_body(request)
    if err:
        return err

    homework = _homework_by_slug(course, homework_slug)
    created = homework is None

    error = _validate_homework_upsert(data, homework, created)
    if error:
        return error

    homework, error = _save_homework_upsert(
        course, homework_slug, data, homework, created
    )
    if error:
        return error

    return JsonResponse(
        _homework_to_dict(homework), status=201 if created else 200
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
    return detail_response(
        request,
        homework,
        to_dict=_homework_to_dict,
        allowed_fields=HOMEWORK_PATCH_FIELDS,
        valid_states=VALID_HOMEWORK_STATES,
        invalid_state_code="invalid_homework_state",
        date_fields={"due_date"},
        closed_state=HomeworkState.CLOSED.value,
        related_queryset=homework.submission_set.all(),
        related_name="submissions",
        noun="homework",
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
