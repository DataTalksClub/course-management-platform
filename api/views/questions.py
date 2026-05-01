import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from courses.models import Course, Homework, Question

from api.safety import error_response, ensure_no_related_records_for_delete
from api.utils import parse_json_body, require_methods


def _question_to_dict(q):
    answers_count = q.answer_set.count()
    return {
        "id": q.id,
        "text": q.text,
        "question_type": q.question_type,
        "answer_type": q.answer_type,
        "possible_answers": q.get_possible_answers(),
        "correct_answer": q.correct_answer,
        "scores_for_correct_answer": q.scores_for_correct_answer,
        "answers_count": answers_count,
        "can_delete": answers_count == 0,
        "delete_blockers": ["has_answers"] if answers_count else [],
    }


def _get_course_and_homework(course_slug, homework_id):
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(Homework, course=course, id=homework_id)
    return course, homework


def _create_question(homework, q_data):
    """Create a single question. Returns (dict, None) or (None, error_str)."""
    text = q_data.get("text")
    if not text:
        return None, "text is required"

    question = Question.objects.create(
        homework=homework,
        text=text,
        question_type=q_data.get("question_type", "FF"),
        answer_type=q_data.get("answer_type"),
        possible_answers="\n".join(q_data.get("possible_answers", [])),
        correct_answer=q_data.get("correct_answer", ""),
        scores_for_correct_answer=q_data.get("scores_for_correct_answer", 1),
    )

    return _question_to_dict(question), None


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def questions_view(request, course_slug, homework_id):
    """
    GET /api/courses/<slug>/homeworks/<id>/questions/ - List questions.
    POST /api/courses/<slug>/homeworks/<id>/questions/ - Add questions.
    """
    course, homework = _get_course_and_homework(course_slug, homework_id)

    if request.method == "GET":
        questions = Question.objects.filter(homework=homework).order_by("id")
        return JsonResponse({
            "homework_id": homework.id,
            "homework_title": homework.title,
            "questions": [_question_to_dict(q) for q in questions],
        })

    # POST
    data, err = parse_json_body(request)
    if err:
        return err

    items = data if isinstance(data, list) else [data]

    created = []
    errors = []
    for item in items:
        q_dict, error = _create_question(homework, item)
        if error:
            errors.append({"text": item.get("text", "unknown"), "error": error})
        else:
            created.append(q_dict)

    result = {"created": created}
    if errors:
        result["errors"] = errors

    status = 201 if created else 400
    return JsonResponse(result, status=status)


QUESTION_PATCH_FIELDS = {
    "text", "question_type", "answer_type",
    "possible_answers", "correct_answer", "scores_for_correct_answer",
}


@token_required
@csrf_exempt
@require_methods("GET", "PATCH", "DELETE")
def question_detail_view(request, course_slug, homework_id, question_id):
    """
    GET /api/courses/<slug>/homeworks/<id>/questions/<id>/ - Question detail.
    PATCH /api/courses/<slug>/homeworks/<id>/questions/<id>/ - Update question.
    DELETE /api/courses/<slug>/homeworks/<id>/questions/<id>/ - Delete question.
    """
    course, homework = _get_course_and_homework(course_slug, homework_id)
    question = get_object_or_404(Question, homework=homework, id=question_id)

    if request.method == "GET":
        return JsonResponse(_question_to_dict(question))

    if request.method == "DELETE":
        error_response_result = ensure_no_related_records_for_delete(
            question.answer_set.all(), "answers", "question"
        )
        if error_response_result:
            return error_response_result

        question.delete()
        return JsonResponse({"deleted": True})

    # PATCH
    data, err = parse_json_body(request)
    if err:
        return err

    for field, value in data.items():
        if field not in QUESTION_PATCH_FIELDS:
            return error_response(
                f"Cannot update field: {field}",
                "invalid_field",
                details={"field": field},
            )

        if field == "possible_answers":
            if isinstance(value, list):
                value = "\n".join(value)

        setattr(question, field, value)

    question.save()
    return JsonResponse(_question_to_dict(question))
