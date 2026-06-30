from dataclasses import dataclass
from typing import List, Optional

from django.http import HttpRequest

from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import ValidationError
from django.db import transaction

from courses.models import (
    Course,
    Homework,
    HomeworkState,
    Question,
    Answer,
    Submission,
    Enrollment,
    User,
)

from courses.views.homework_statistics import (
    homework_statistics as homework_statistics,
)
from courses.views.homework_submissions import (
    homework_submissions as homework_submissions,
)
from courses.views.homework_answers import (
    process_question_options,
)
from courses.views.homework_submission import (
    HomeworkPostData,
    process_homework_submission,
)


@dataclass(frozen=True)
class HomeworkRequestData:
    request: HttpRequest
    course: Course
    homework: Homework
    questions: List[Question]


@dataclass(frozen=True)
class HomeworkDetailContextData:
    course: Course
    homework: Homework
    questions: List[Question]
    submission: Optional[Submission]
    enrollment: Optional[Enrollment]


@dataclass(frozen=True)
class HomeworkDetailObjects:
    course: Course
    homework: Homework
    questions: List[Question]


@dataclass(frozen=True)
class AuthenticatedHomeworkContext:
    context: dict
    submission: Optional[Submission]
    enrollment: Enrollment


def homework_detail_build_context_not_authenticated(
    course: Course,
    homework: Homework,
    questions: List[Question],
) -> dict:
    context = {
        "course": course,
        "homework": homework,
        "question_answers": question_answers_for_submission(
            homework,
            questions,
            None,
        ),
        "is_authenticated": False,
        "disabled": True,
        "accepting_submissions": (
            homework.state == HomeworkState.OPEN.value
        ),
    }

    return context


def submission_answer_map(
    submission: Optional[Submission],
) -> dict[int, Answer]:
    if not submission:
        return {}

    answers = Answer.objects.filter(
        submission=submission
    ).select_related("question")
    answer_map = {}
    for answer in answers:
        answer_map[answer.question.id] = answer
    return answer_map


def question_answers_for_submission(
    homework: Homework,
    questions: List[Question],
    submission: Optional[Submission],
) -> list[tuple[Question, dict]]:
    question_answers_map = submission_answer_map(submission)
    question_answers = []

    for question in questions:
        answer = question_answers_map.get(question.id)
        processed_answer = process_question_options(
            homework,
            question,
            answer,
        )
        question_answer = (question, processed_answer)
        question_answers.append(question_answer)

    return question_answers


def learning_in_public_disabled(
    enrollment: Optional["Enrollment"],
) -> bool:
    return (
        enrollment.disable_learning_in_public if enrollment else False
    )


def homework_detail_build_context_authenticated(data) -> dict:
    context = {
        "course": data.course,
        "homework": data.homework,
        "question_answers": question_answers_for_submission(
            data.homework,
            data.questions,
            data.submission,
        ),
        "submission": data.submission,
        "is_authenticated": True,
        "disable_learning_in_public": learning_in_public_disabled(
            data.enrollment
        ),
    }
    context.update(homework_state_context(data.homework))
    return context


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


def homework_state_context(homework: Homework) -> dict[str, bool]:
    accepting_submissions = homework.state == HomeworkState.OPEN.value
    return {
        "disabled": not accepting_submissions,
        "accepting_submissions": accepting_submissions,
    }


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


def _post_preview_value(request: HttpRequest, key: str) -> str:
    return request.POST.get(key, "")


def _post_preview_learning_links(request: HttpRequest) -> list[str]:
    links = []
    raw_links = request.POST.getlist("learning_in_public_links[]")
    for raw_link in raw_links:
        link = raw_link.strip()
        if link:
            links.append(link)
    return links


def _apply_post_preview_homework_url(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.homework_url_field:
        submission.homework_link = _post_preview_value(
            request,
            "homework_url",
        )


def _apply_post_preview_learning_links(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.learning_in_public_cap > 0:
        submission.learning_in_public_links = (
            _post_preview_learning_links(request)
        )


def _apply_post_preview_time_spent(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.time_spent_lectures_field:
        submission.time_spent_lectures = _post_preview_value(
            request,
            "time_spent_lectures",
        )

    if homework.time_spent_homework_field:
        submission.time_spent_homework = _post_preview_value(
            request,
            "time_spent_homework",
        )


def _apply_post_preview_comments(
    request: HttpRequest,
    course: Course,
    submission: Submission,
) -> None:
    if course.homework_problems_comments_field:
        submission.problems_comments = _post_preview_value(
            request,
            "problems_comments",
        )


def _apply_post_preview_faq_contribution(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.faq_contribution_field:
        submission.faq_contribution_url = _post_preview_value(
            request,
            "faq_contribution_url",
        )


def apply_homework_post_preview_fields(
    request: HttpRequest,
    course: Course,
    homework: Homework,
    submission: Submission,
) -> None:
    _apply_post_preview_homework_url(request, homework, submission)
    _apply_post_preview_learning_links(request, homework, submission)
    _apply_post_preview_time_spent(request, homework, submission)
    _apply_post_preview_comments(request, course, submission)
    _apply_post_preview_faq_contribution(request, homework, submission)


def question_answers_from_post(
    request: HttpRequest,
    homework: Homework,
    questions: List[Question],
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
    context = {
        "course": data.course,
        "homework": data.homework,
        "question_answers": question_answers_from_post(
            data.request,
            data.homework,
            data.questions,
        ),
        "submission": bound_submission,
        "is_authenticated": True,
        "disable_learning_in_public": (
            data.enrollment.disable_learning_in_public
        ),
    }
    context.update(homework_state_context(data.homework))
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


def redirect_to_homework(course: Course, homework: Homework):
    return redirect(
        "homework",
        course_slug=course.slug,
        homework_slug=homework.slug,
    )


def closed_homework_submission_response(
    request: HttpRequest,
    course: Course,
    homework: Homework,
):
    messages.error(
        request,
        "This homework is not open for submissions.",
        extra_tags="homework",
    )
    return redirect_to_homework(course, homework)


def homework_validation_context(
    data: HomeworkPostData,
    error: ValidationError,
) -> dict:
    context = homework_detail_build_context_from_post(data)
    context["errors"] = error.messages
    context["error_fields"] = homework_error_fields(error)
    return context


def handle_homework_post(data: HomeworkPostData):
    if data.homework.state != HomeworkState.OPEN.value:
        return closed_homework_submission_response(
            data.request,
            data.course,
            data.homework,
        )

    try:
        with transaction.atomic():
            return process_homework_submission(data)
    except ValidationError as error:
        return homework_validation_context(
            data=data,
            error=error,
        )


def homework_detail_objects(course_slug: str, homework_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework,
        course=course,
        slug=homework_slug,
    )
    questions = Question.objects.filter(homework=homework).order_by(
        "id"
    )
    return HomeworkDetailObjects(
        course=course,
        homework=homework,
        questions=questions,
    )


def authenticated_homework_context(
    user: User,
    course: Course,
    homework: Homework,
    questions: List[Question],
):
    submission = Submission.objects.filter(
        homework=homework,
        student=user,
    ).first()
    enrollment, _ = Enrollment.objects.get_or_create(
        student=user,
        course=course,
    )
    context_data = HomeworkDetailContextData(
        course=course,
        homework=homework,
        questions=questions,
        submission=submission,
        enrollment=enrollment,
    )
    context = homework_detail_build_context_authenticated(context_data)
    return AuthenticatedHomeworkContext(
        context=context,
        submission=submission,
        enrollment=enrollment,
    )


def authenticated_homework_response(data: HomeworkRequestData):
    authenticated_context = authenticated_homework_context(
        user=data.request.user,
        course=data.course,
        homework=data.homework,
        questions=data.questions,
    )

    if data.request.method != "POST":
        return render(
            data.request,
            "homework/homework.html",
            authenticated_context.context,
        )

    return authenticated_homework_post_response(
        data,
        authenticated_context,
    )


def authenticated_homework_post_response(
    data: HomeworkRequestData,
    authenticated_context: AuthenticatedHomeworkContext,
):
    post_data = HomeworkPostData(
        request=data.request,
        course=data.course,
        homework=data.homework,
        questions=data.questions,
        submission=authenticated_context.submission,
        enrollment=authenticated_context.enrollment,
    )
    post_result = handle_homework_post(post_data)
    if not isinstance(post_result, dict):
        return post_result

    return render(data.request, "homework/homework.html", post_result)


def homework_view(
    request: HttpRequest, course_slug: str, homework_slug: str
):
    detail_objects = homework_detail_objects(
        course_slug,
        homework_slug,
    )
    course = detail_objects.course
    homework = detail_objects.homework
    questions = detail_objects.questions
    user = request.user

    if not user.is_authenticated:
        context = homework_detail_build_context_not_authenticated(
            course=course, homework=homework, questions=questions
        )
        return render(request, "homework/homework.html", context)

    request_data = HomeworkRequestData(
        request=request,
        course=course,
        homework=homework,
        questions=questions,
    )
    return authenticated_homework_response(request_data)
