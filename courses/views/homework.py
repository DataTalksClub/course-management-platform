import logging

from dataclasses import dataclass
from typing import List, Optional

from django.http import HttpRequest

from django.contrib import messages
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import ValidationError
from django.db import transaction

from course_management.datamailer import sync_homework_submission_to_datamailer
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

from courses.validators import clean_faq_contribution_url
from courses.views.homework_confirmation import (
    HomeworkConfirmationEmailData,
    build_homework_update_url,
    send_homework_confirmation_email,
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
from courses.views.homework_learning_links import (
    clean_learning_in_public_links,
    find_duplicate_learning_in_public_links,
)
from courses.views.submission_formatting import parse_time_spent_hours

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HomeworkPostData:
    request: HttpRequest
    course: Course
    homework: Homework
    questions: List[Question]
    submission: Optional[Submission]
    enrollment: Enrollment


@dataclass(frozen=True)
class HomeworkRequestData:
    request: HttpRequest
    course: Course
    homework: Homework
    questions: List[Question]


@dataclass(frozen=True)
class HomeworkSubmissionFieldData:
    submission: Submission
    request: HttpRequest
    course: Course
    homework: Homework
    user: User


@dataclass(frozen=True)
class HomeworkTimeSpentFieldData:
    submission: Submission
    request: HttpRequest
    enabled: bool
    post_key: str
    model_field: str
    field_label: str


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


def _apply_homework_submission_fields(field_data):
    """Populate the optional submission fields enabled for this homework."""
    _apply_homework_url_field(field_data)
    _apply_learning_in_public_links(field_data)
    _apply_time_spent_fields(field_data)
    _apply_problems_comments_field(field_data)
    _apply_faq_contribution_field(field_data)


def _apply_homework_url_field(field_data):
    if field_data.homework.homework_url_field:
        field_data.submission.homework_link = (
            field_data.request.POST.get("homework_url")
        )


def _apply_learning_in_public_links(field_data):
    if field_data.homework.learning_in_public_cap > 0:
        links = field_data.request.POST.getlist(
            "learning_in_public_links[]"
        )
        cleaned_links = clean_learning_in_public_links(
            links,
            field_data.homework.learning_in_public_cap,
        )
        duplicate_links = find_duplicate_learning_in_public_links(
            user=field_data.user,
            course=field_data.course,
            links=cleaned_links,
            current_submission=field_data.submission,
        )
        if duplicate_links:
            raise ValidationError(
                "Learning in public links were already used in another "
                f"submission: {', '.join(duplicate_links)}"
            )
        field_data.submission.learning_in_public_links = cleaned_links


def _apply_time_spent_fields(field_data):
    lectures_field_data = HomeworkTimeSpentFieldData(
        submission=field_data.submission,
        request=field_data.request,
        enabled=field_data.homework.time_spent_lectures_field,
        post_key="time_spent_lectures",
        model_field="time_spent_lectures",
        field_label="time spent on lectures",
    )
    _apply_time_spent_field(lectures_field_data)

    homework_field_data = HomeworkTimeSpentFieldData(
        submission=field_data.submission,
        request=field_data.request,
        enabled=field_data.homework.time_spent_homework_field,
        post_key="time_spent_homework",
        model_field="time_spent_homework",
        field_label="time spent on homework",
    )
    _apply_time_spent_field(homework_field_data)


def _apply_time_spent_field(data):
    if not data.enabled:
        return

    time_spent = parse_time_spent_hours(
        data.request.POST.get(data.post_key),
        data.field_label,
    )
    if time_spent is not None:
        setattr(data.submission, data.model_field, time_spent)


def _apply_problems_comments_field(field_data):
    if field_data.course.homework_problems_comments_field:
        field_data.submission.problems_comments = (
            field_data.request.POST.get(
                "problems_comments",
                "",
            ).strip()
        )


def _apply_faq_contribution_field(field_data):
    if field_data.homework.faq_contribution_field:
        field_data.submission.faq_contribution_url = (
            clean_faq_contribution_url(
                field_data.request.POST.get("faq_contribution_url", "")
            ).strip()
        )


def _homework_answers_from_post(request):
    answers_dict = {}
    posted_answers = request.POST.lists()
    for answer_id, answer in posted_answers:
        if not answer_id.startswith("answer_"):
            continue
        cleaned_answer_items = []
        for answer_item in answer:
            cleaned_answer_item = answer_item.strip()
            cleaned_answer_items.append(cleaned_answer_item)
        answers_dict[answer_id] = ",".join(cleaned_answer_items)
    return answers_dict


def _homework_submission_for_user(user, course, homework, submission):
    if submission:
        submission.submitted_at = timezone.now()
        return submission

    enrollment, _ = Enrollment.objects.get_or_create(
        student=user,
        course=course,
    )
    return Submission.objects.create(
        homework=homework,
        student=user,
        enrollment=enrollment,
    )


def _save_homework_answers(submission, questions, answers_dict):
    for question in questions:
        answer_text = answers_dict.get(f"answer_{question.id}")
        Answer.objects.update_or_create(
            submission=submission,
            question=question,
            defaults={"answer_text": answer_text},
        )


def _register_homework_submission_callbacks(data, submission):
    user = data.request.user
    update_url = build_homework_update_url(
        data.request,
        data.course,
        data.homework,
    )
    confirmation_data = HomeworkConfirmationEmailData(
        user=user,
        course=data.course,
        homework=data.homework,
        submission=submission,
        update_url=update_url,
    )
    transaction.on_commit(
        lambda: send_homework_confirmation_email(confirmation_data)
    )
    transaction.on_commit(
        lambda: sync_homework_submission_to_datamailer(submission)
    )


def _homework_submission_success_response(request, course, homework):
    success_message = (
        "Thank you for submitting your homework, now your solution "
        + "is saved. You can update it at any point. You will see "
        + "your score after the form is closed."
    )
    messages.success(
        request,
        success_message,
        extra_tags="homework",
    )
    return redirect(
        "homework",
        course_slug=course.slug,
        homework_slug=homework.slug,
    )


def _save_homework_submission_data(data):
    user = data.request.user
    answers_dict = _homework_answers_from_post(data.request)
    submission = _homework_submission_for_user(
        user,
        data.course,
        data.homework,
        data.submission,
    )
    _save_homework_answers(submission, data.questions, answers_dict)
    field_data = HomeworkSubmissionFieldData(
        submission=submission,
        request=data.request,
        course=data.course,
        homework=data.homework,
        user=user,
    )
    _apply_homework_submission_fields(field_data)
    submission.full_clean()
    submission.save()
    return submission


def process_homework_submission(data: HomeworkPostData):
    submission = _save_homework_submission_data(data)
    _register_homework_submission_callbacks(data, submission)
    return _homework_submission_success_response(
        data.request,
        data.course,
        data.homework,
    )


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


def submit_homework_post(
    data: HomeworkPostData,
):
    with transaction.atomic():
        return process_homework_submission(data)


def handle_homework_post(data: HomeworkPostData):
    if data.homework.state != HomeworkState.OPEN.value:
        return closed_homework_submission_response(
            data.request,
            data.course,
            data.homework,
        )

    try:
        return submit_homework_post(data)
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
