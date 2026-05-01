import json

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.text import slugify

from accounts.auth import token_required
from courses.models import Course, Homework, Question
from courses.models.homework import HomeworkState

from api.safety import (
    error_response,
    ensure_closed_for_delete,
    ensure_no_related_records_for_delete,
)
from api.utils import parse_date, parse_json_body, require_methods


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


def _create_homework(course, hw_data):
    """Create a homework. Returns (dict, None) or (None, error_str)."""
    name = hw_data.get("name")
    due_date_str = hw_data.get("due_date")

    if not name or not due_date_str:
        return None, "name and due_date are required"

    due_date = parse_date(due_date_str)
    if due_date is None:
        return None, f"Invalid date format: {due_date_str}"

    slug = hw_data.get("slug") or slugify(name)

    if Homework.objects.filter(course=course, slug=slug).exists():
        return None, f"Homework with slug '{slug}' already exists"

    homework = Homework.objects.create(
        course=course,
        slug=slug,
        title=name,
        description=hw_data.get("description", ""),
        due_date=due_date,
        state=HomeworkState.CLOSED.value,
    )

    # Create questions if provided
    questions_data = hw_data.get("questions", [])
    for q_data in questions_data:
        Question.objects.create(
            homework=homework,
            text=q_data.get("text", ""),
            question_type=q_data.get("question_type", "FF"),
            answer_type=q_data.get("answer_type"),
            possible_answers="\n".join(q_data.get("possible_answers", [])),
            correct_answer=q_data.get("correct_answer", ""),
            scores_for_correct_answer=q_data.get("scores_for_correct_answer", 1),
        )

    return _homework_to_dict(homework), None


def _create_question(homework, q_data):
    Question.objects.create(
        homework=homework,
        text=q_data.get("text", ""),
        question_type=q_data.get("question_type", "FF"),
        answer_type=q_data.get("answer_type"),
        possible_answers="\n".join(q_data.get("possible_answers", [])),
        correct_answer=q_data.get("correct_answer", ""),
        scores_for_correct_answer=q_data.get("scores_for_correct_answer", 1),
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
        homeworks = Homework.objects.filter(course=course).order_by("id")
        return JsonResponse({
            "homeworks": [_homework_to_dict(hw) for hw in homeworks],
        })

    # POST
    data, err = parse_json_body(request)
    if err:
        return err

    # Support both single object and list
    items = data if isinstance(data, list) else [data]

    created = []
    errors = []
    for item in items:
        hw_dict, error = _create_homework(course, item)
        if error:
            errors.append({"name": item.get("name", "unknown"), "error": error})
        else:
            created.append(hw_dict)

    result = {"created": created}
    if errors:
        result["errors"] = errors

    status = 201 if created else 400
    return JsonResponse(result, status=status)


HOMEWORK_PATCH_FIELDS = {
    "title", "description", "due_date", "state",
    "learning_in_public_cap", "homework_url_field",
    "time_spent_lectures_field", "time_spent_homework_field",
    "faq_contribution_field",
}

VALID_HOMEWORK_STATES = {s.value for s in HomeworkState}


def _apply_homework_data(homework, data):
    title = data.get("title", data.get("name"))
    if title is not None:
        homework.title = title

    if "description" in data:
        homework.description = data["description"]

    if "due_date" in data:
        due_date = parse_date(data["due_date"])
        if due_date is None:
            return error_response(
                "Invalid date format for due_date",
                "invalid_date_format",
                details={"field": "due_date"},
            )
        homework.due_date = due_date

    for field in (
        "state",
        "learning_in_public_cap",
        "homework_url_field",
        "time_spent_lectures_field",
        "time_spent_homework_field",
        "faq_contribution_field",
    ):
        if field not in data:
            continue
        value = data[field]
        if field == "state" and value not in VALID_HOMEWORK_STATES:
            return error_response(
                f"Invalid state. Must be one of: {sorted(VALID_HOMEWORK_STATES)}",
                "invalid_homework_state",
                details={"valid_states": sorted(VALID_HOMEWORK_STATES)},
            )
        setattr(homework, field, value)

    return None


def _homework_questions_replace_error(homework):
    if _homework_delete_blockers(homework):
        return error_response(
            "Questions can only be replaced for closed homeworks with no submissions",
            "homework_questions_replace_blocked",
            details={"delete_blockers": _homework_delete_blockers(homework)},
        )

    answered_questions = homework.question_set.filter(
        answer__isnull=False
    ).distinct()
    if answered_questions.exists():
        return error_response(
            "Cannot replace questions with existing answers",
            "homework_questions_have_answers",
            details={"answered_questions_count": answered_questions.count()},
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


def _upsert_homework_by_slug(request, course_slug, homework_slug):
    course = get_object_or_404(Course, slug=course_slug)
    data, err = parse_json_body(request)
    if err:
        return err

    homework = Homework.objects.filter(
        course=course,
        slug=homework_slug,
    ).first()
    created = homework is None

    title = data.get("title", data.get("name"))
    if created and (not title or not data.get("due_date")):
        return error_response(
            "title/name and due_date are required",
            "missing_required_fields",
        )

    if "due_date" in data and parse_date(data["due_date"]) is None:
        return error_response(
            "Invalid date format for due_date",
            "invalid_date_format",
            details={"field": "due_date"},
        )

    if "state" in data and data["state"] not in VALID_HOMEWORK_STATES:
        return error_response(
            f"Invalid state. Must be one of: {sorted(VALID_HOMEWORK_STATES)}",
            "invalid_homework_state",
            details={"valid_states": sorted(VALID_HOMEWORK_STATES)},
        )

    if homework is not None and "questions" in data:
        error = _homework_questions_replace_error(homework)
        if error:
            return error

    with transaction.atomic():
        if created:
            homework = Homework.objects.create(
                course=course,
                slug=homework_slug,
                title=title,
                description=data.get("description", ""),
                due_date=parse_date(data["due_date"]),
                state=HomeworkState.CLOSED.value,
            )

        error = _apply_homework_data(homework, data)
        if error:
            return error

        homework.save()

        if "questions" in data:
            error = _replace_homework_questions(homework, data["questions"])
            if error:
                return error

    return JsonResponse(_homework_to_dict(homework), status=201 if created else 200)


def _homework_detail_response(
    request,
    course_slug,
    *,
    homework_id=None,
    homework_slug=None,
):
    course = get_object_or_404(Course, slug=course_slug)
    if homework_id is not None:
        homework = get_object_or_404(Homework, course=course, id=homework_id)
    else:
        homework = get_object_or_404(Homework, course=course, slug=homework_slug)

    if request.method == "GET":
        return JsonResponse(_homework_to_dict(homework))

    if request.method == "DELETE":
        error_response_result = ensure_closed_for_delete(
            homework, HomeworkState.CLOSED.value, "homework"
        )
        if error_response_result:
            return error_response_result

        error_response_result = ensure_no_related_records_for_delete(
            homework.submission_set.all(), "submissions", "homework"
        )
        if error_response_result:
            return error_response_result

        homework.delete()
        return JsonResponse({"deleted": True})

    data, err = parse_json_body(request)
    if err:
        return err

    for field, value in data.items():
        if field not in HOMEWORK_PATCH_FIELDS:
            return error_response(
                f"Cannot update field: {field}",
                "invalid_field",
                details={"field": field},
            )

        if field == "state":
            if value not in VALID_HOMEWORK_STATES:
                return error_response(
                    f"Invalid state. Must be one of: {sorted(VALID_HOMEWORK_STATES)}",
                    "invalid_homework_state",
                    details={"valid_states": sorted(VALID_HOMEWORK_STATES)},
                )

        if field == "due_date":
            value = parse_date(value)
            if value is None:
                return error_response(
                    "Invalid date format for due_date",
                    "invalid_date_format",
                    details={"field": "due_date"},
                )

        setattr(homework, field, value)

    homework.save()
    return JsonResponse(_homework_to_dict(homework))


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
        return _upsert_homework_by_slug(request, course_slug, homework_slug)

    return _homework_detail_response(
        request, course_slug, homework_slug=homework_slug
    )
