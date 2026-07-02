from typing import Any

from courses.models.homework import Answer, Question, Submission
from courses.views.homework_answer_formatting import (
    extract_selected_option_indexes,
    format_selected_answer,
    selected_option_value,
)
from courses.views.homework_answers import CHOICE_QUESTION_TYPES


def homework_submitted_answers(
    submission: Submission,
) -> list[dict[str, Any]]:
    answer_payloads = []
    answers = Answer.objects.filter(submission=submission)
    answers = answers.select_related("question")
    answers = answers.order_by("question_id")
    for answer in answers:
        payload = submitted_answer_payload(answer)
        answer_payloads.append(payload)
    return answer_payloads


def submitted_answer_payload(answer: Answer) -> dict[str, Any]:
    question = answer.question
    raw_answer = answer.answer_text or ""
    display_answer, selected_options = submitted_answer_display(
        question,
        raw_answer,
    )

    return {
        "question_id": question.id,
        "question": question.text,
        "question_type": question.question_type,
        "answer": display_answer,
        "raw_answer": raw_answer,
        "selected_options": selected_options,
    }


def submitted_answer_display(
    question: Question,
    raw_answer: str,
) -> tuple[str, list[dict[str, Any]]]:
    if question.question_type not in CHOICE_QUESTION_TYPES:
        return raw_answer, []

    selected_options = submitted_selected_options(question, raw_answer)
    display_answer = format_selected_answer(question, raw_answer)
    return display_answer, selected_options


def submitted_selected_options(
    question: Question,
    raw_answer: str,
) -> list[dict[str, Any]]:
    possible_answers = question.get_possible_answers()
    selected_options = []
    selected_indexes = extract_selected_option_indexes(raw_answer)
    for index in selected_indexes:
        selected_value = selected_option_value(possible_answers, index)
        option = {
            "index": index,
            "value": selected_value,
        }
        selected_options.append(option)
    return selected_options
