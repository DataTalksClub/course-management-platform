from django.http import JsonResponse

from api.safety import (
    error_response,
    ensure_no_related_records_for_delete,
)
from api.utils import parse_json_body
from courses.models.homework import Question

from .question_serializers import question_to_dict

QUESTION_PATCH_FIELDS = {
    "text",
    "question_type",
    "answer_type",
    "possible_answers",
    "correct_answer",
    "scores_for_correct_answer",
}


def create_question(homework, question_data):
    text = question_data.get("text")
    if not text:
        return None, "text is required"

    question_type = question_data.get("question_type", "FF")
    answer_type = question_data.get("answer_type")
    possible_answer_values = question_data.get("possible_answers", [])
    possible_answers = "\n".join(possible_answer_values)
    correct_answer = question_data.get("correct_answer", "")
    scores_for_correct_answer = question_data.get(
        "scores_for_correct_answer",
        1,
    )
    question = Question.objects.create(
        homework=homework,
        text=text,
        question_type=question_type,
        answer_type=answer_type,
        possible_answers=possible_answers,
        correct_answer=correct_answer,
        scores_for_correct_answer=scores_for_correct_answer,
    )

    question_record = question_to_dict(question)
    return question_record, None


def question_create_items(data):
    if isinstance(data, list):
        return data
    item_list = [data]
    return item_list


def question_create_error(item, error):
    text = item.get("text", "unknown")
    return {"text": text, "error": error}


def questions_create_response(homework, data):
    created = []
    errors = []

    question_items = question_create_items(data)
    for item in question_items:
        question_record, error = create_question(homework, item)
        if error:
            question_error = question_create_error(item, error)
            errors.append(question_error)
        else:
            created.append(question_record)

    result = {"created": created}
    if errors:
        result["errors"] = errors

    if created:
        status = 201
    else:
        status = 400
    response = JsonResponse(result, status=status)
    return response


def question_delete_response(question):
    answer_records = question.answer_set.all()
    error_response_result = ensure_no_related_records_for_delete(
        answer_records, "answers", "question"
    )
    if error_response_result:
        return error_response_result

    question.delete()
    payload = {"deleted": True}
    response = JsonResponse(payload)
    return response


def question_patch_value(field, value):
    if field == "possible_answers" and isinstance(value, list):
        return "\n".join(value)
    return value


def question_invalid_field_response(field):
    details = {"field": field}
    return error_response(
        f"Cannot update field: {field}",
        "invalid_field",
        details=details,
    )


def apply_question_patch(question, data):
    for field, value in data.items():
        if field not in QUESTION_PATCH_FIELDS:
            return question_invalid_field_response(field)

        patch_value = question_patch_value(field, value)
        setattr(question, field, patch_value)

    return None


def question_patch_response(question, request):
    data, err = parse_json_body(request)
    if err:
        return err

    error = apply_question_patch(question, data)
    if error:
        return error

    question.save()
    question_record = question_to_dict(question)
    response = JsonResponse(question_record)
    return response
