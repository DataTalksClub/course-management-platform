from django.core.exceptions import ValidationError
from django.http import HttpRequest

from courses.models.homework import Answer, Homework, Question, Submission
from courses.views.homework_answers import process_question_options
from courses.views.homework_context import homework_state_context
from courses.views.homework_post_fields import (
    apply_homework_post_preview_fields,
)
from courses.views.homework_submission import HomeworkPostData


def answer_from_post(
    request: HttpRequest, question: Question
) -> Answer:
    answer_values = []
    post_values = request.POST.getlist(f"answer_{question.id}")
    for value in post_values:
        answer_value = value.strip()
        answer_values.append(answer_value)
    answer_text = ",".join(answer_values)
    return Answer(question=question, answer_text=answer_text)


def bound_homework_submission_from_post(
    data: HomeworkPostData,
) -> Submission:
    bound_submission = data.submission or Submission(
        homework=data.homework,
        student=data.request.user,
        enrollment=data.enrollment,
    )
    apply_homework_post_preview_fields(
        data.request,
        data.course,
        data.homework,
        bound_submission,
    )
    return bound_submission


def question_answers_from_post(
    request: HttpRequest,
    homework: Homework,
    questions: list[Question],
) -> list[tuple[Question, dict]]:
    question_answers = []
    for question in questions:
        answer = answer_from_post(request, question)
        processed_answer = process_question_options(
            homework,
            question,
            answer,
        )
        question_answer = (question, processed_answer)
        question_answers.append(question_answer)
    return question_answers


def homework_detail_build_context_from_post(
    data: HomeworkPostData,
) -> dict:
    bound_submission = bound_homework_submission_from_post(data)
    question_answers = question_answers_from_post(
        data.request,
        data.homework,
        data.questions,
    )
    disable_learning_in_public = data.enrollment.disable_learning_in_public
    state_context = homework_state_context(data.homework)
    context = {
        "course": data.course,
        "homework": data.homework,
        "question_answers": question_answers,
        "submission": bound_submission,
        "is_authenticated": True,
        "disable_learning_in_public": disable_learning_in_public,
    }
    context.update(state_context)
    return context


def homework_error_fields(error: ValidationError) -> set[str]:
    field_map = {
        "homework_link": "homework_url",
        "learning_in_public_links": "learning_in_public_links",
        "time_spent_lectures": "time_spent_lectures",
        "time_spent_homework": "time_spent_homework",
        "problems_comments": "problems_comments",
        "faq_contribution_url": "faq_contribution_url",
    }

    if not hasattr(error, "message_dict"):
        return set()

    fields = set()
    error_field_names = error.message_dict
    for field_name in error_field_names:
        if field_name in field_map:
            field = field_map[field_name]
            fields.add(field)
    return fields


def homework_validation_context(
    data: HomeworkPostData,
    error: ValidationError,
) -> dict:
    context = homework_detail_build_context_from_post(data)
    context["errors"] = error.messages
    context["error_fields"] = homework_error_fields(error)
    return context
