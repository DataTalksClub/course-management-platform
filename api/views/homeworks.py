import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.text import slugify

from accounts.auth import token_required
from courses.models import Course, Homework, Question
from courses.models.homework import HomeworkState

from api.utils import parse_date, parse_json_body, require_methods


def _homework_to_dict(hw):
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
    }


def _create_homework(course, hw_data):
    """Create a single homework from a data dict. Returns (dict, None) or (None, error_str)."""
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


@token_required
@csrf_exempt
@require_methods("PATCH", "DELETE")
def homework_detail_view(request, course_slug, homework_id):
    """
    PATCH /api/courses/<slug>/homeworks/<id>/ - Update homework.
    DELETE /api/courses/<slug>/homeworks/<id>/ - Delete homework (closed only).
    """
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(Homework, course=course, id=homework_id)

    if request.method == "DELETE":
        if homework.state != HomeworkState.CLOSED.value:
            return JsonResponse(
                {"error": "Only closed homeworks can be deleted"},
                status=400,
            )
        homework.delete()
        return JsonResponse({"deleted": True})

    # PATCH
    data, err = parse_json_body(request)
    if err:
        return err

    for field, value in data.items():
        if field not in HOMEWORK_PATCH_FIELDS:
            return JsonResponse(
                {"error": f"Cannot update field: {field}"},
                status=400,
            )

        if field == "state":
            if value not in VALID_HOMEWORK_STATES:
                return JsonResponse(
                    {"error": f"Invalid state. Must be one of: {sorted(VALID_HOMEWORK_STATES)}"},
                    status=400,
                )

        if field == "due_date":
            value = parse_date(value)
            if value is None:
                return JsonResponse(
                    {"error": f"Invalid date format for due_date"},
                    status=400,
                )

        setattr(homework, field, value)

    homework.save()
    return JsonResponse(_homework_to_dict(homework))
