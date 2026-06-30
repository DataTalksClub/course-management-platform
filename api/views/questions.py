
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from courses.models import Course, Homework, Question

from api.safety import (
    error_response,
    ensure_no_related_records_for_delete,
    require_staff_token,
)
from api.utils import parse_json_body, require_methods


def _question_to_dict(q):
    answers_count = q.answer_set.count()
    possible_answers = q.get_possible_answers()
    return {
        "id": q.id,
        "text": q.text,
        "question_type": q.question_type,
        "answer_type": q.answer_type,
        "possible_answers": possible_answers,
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

    question_type = q_data.get("question_type", "FF")
    answer_type = q_data.get("answer_type")
    possible_answer_values = q_data.get("possible_answers", [])
    possible_answers = "\n".join(possible_answer_values)
    correct_answer = q_data.get("correct_answer", "")
    scores_for_correct_answer = q_data.get("scores_for_correct_answer", 1)
    question = Question.objects.create(
        homework=homework,
        text=text,
        question_type=question_type,
        answer_type=answer_type,
        possible_answers=possible_answers,
        correct_answer=correct_answer,
        scores_for_correct_answer=scores_for_correct_answer,
    )

    question_record = _question_to_dict(question)
    return question_record, None


def _questions_list_response(homework):
    questions = Question.objects.filter(homework=homework).order_by("id")
    question_records = []
    for question in questions:
        question_record = _question_to_dict(question)
        question_records.append(question_record)

    payload = {
        "homework_id": homework.id,
        "homework_title": homework.title,
        "questions": question_records,
    }
    return JsonResponse(payload)


def _question_create_items(data):
    return data if isinstance(data, list) else [data]


def _question_create_error(item, error):
    text = item.get("text", "unknown")
    return {"text": text, "error": error}


def _questions_create_response(homework, data):
    created = []
    errors = []

    question_items = _question_create_items(data)
    for item in question_items:
        q_dict, error = _create_question(homework, item)
        if error:
            question_error = _question_create_error(item, error)
            errors.append(question_error)
        else:
            created.append(q_dict)

    result = {"created": created}
    if errors:
        result["errors"] = errors

    status = 201 if created else 400
    return JsonResponse(result, status=status)


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
        return _questions_list_response(homework)

    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    data, err = parse_json_body(request)
    if err:
        return err

    return _questions_create_response(homework, data)


QUESTION_PATCH_FIELDS = {
    "text", "question_type", "answer_type",
    "possible_answers", "correct_answer", "scores_for_correct_answer",
}


def _question_delete_response(question):
    answer_records = question.answer_set.all()
    error_response_result = ensure_no_related_records_for_delete(
        answer_records, "answers", "question"
    )
    if error_response_result:
        return error_response_result

    question.delete()
    payload = {"deleted": True}
    return JsonResponse(payload)


def _question_patch_value(field, value):
    if field == "possible_answers" and isinstance(value, list):
        return "\n".join(value)
    return value


def _question_invalid_field_response(field):
    details = {"field": field}
    return error_response(
        f"Cannot update field: {field}",
        "invalid_field",
        details=details,
    )


def _apply_question_patch(question, data):
    for field, value in data.items():
        if field not in QUESTION_PATCH_FIELDS:
            return _question_invalid_field_response(field)

        patch_value = _question_patch_value(field, value)
        setattr(question, field, patch_value)

    return None


def _question_patch_response(question, request):
    data, err = parse_json_body(request)
    if err:
        return err

    error = _apply_question_patch(question, data)
    if error:
        return error

    question.save()
    question_record = _question_to_dict(question)
    return JsonResponse(question_record)


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
        question_record = _question_to_dict(question)
        return JsonResponse(question_record)

    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    if request.method == "DELETE":
        return _question_delete_response(question)

    return _question_patch_response(question, request)
