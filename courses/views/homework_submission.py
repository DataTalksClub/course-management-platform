from dataclasses import dataclass
from functools import partial

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import redirect
from django.utils import timezone

from course_management.datamailer.sync.memberships import (
    sync_homework_submission_to_datamailer,
)
from courses.models import (
    Answer,
    Course,
    Enrollment,
    Homework,
    Question,
    Submission,
    User,
)
from courses.validators.custom_url_validators import (
    clean_faq_contribution_url,
)
from courses.views.homework_confirmation import (
    HomeworkConfirmationEmailData,
    build_homework_update_url,
    send_homework_confirmation_email,
)
from courses.views.homework_learning_links import (
    clean_learning_in_public_links,
    find_duplicate_learning_in_public_links,
)
from courses.views.submission_formatting import parse_time_spent_hours


@dataclass(frozen=True)
class HomeworkPostData:
    request: HttpRequest
    course: Course
    homework: Homework
    questions: list[Question]
    submission: Submission | None
    enrollment: Enrollment


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


def apply_homework_submission_fields(field_data):
    apply_homework_url_field(field_data)
    apply_learning_in_public_links(field_data)
    apply_time_spent_fields(field_data)
    apply_problems_comments_field(field_data)
    apply_faq_contribution_field(field_data)


def apply_homework_url_field(field_data):
    if field_data.homework.homework_url_field:
        field_data.submission.homework_link = (
            field_data.request.POST.get("homework_url")
        )


def apply_learning_in_public_links(field_data):
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


def apply_time_spent_fields(field_data):
    lectures_field_data = HomeworkTimeSpentFieldData(
        submission=field_data.submission,
        request=field_data.request,
        enabled=field_data.homework.time_spent_lectures_field,
        post_key="time_spent_lectures",
        model_field="time_spent_lectures",
        field_label="time spent on lectures",
    )
    apply_time_spent_field(lectures_field_data)

    homework_field_data = HomeworkTimeSpentFieldData(
        submission=field_data.submission,
        request=field_data.request,
        enabled=field_data.homework.time_spent_homework_field,
        post_key="time_spent_homework",
        model_field="time_spent_homework",
        field_label="time spent on homework",
    )
    apply_time_spent_field(homework_field_data)


def apply_time_spent_field(data):
    if not data.enabled:
        return

    posted_time_spent = data.request.POST.get(data.post_key)
    time_spent = parse_time_spent_hours(
        posted_time_spent,
        data.field_label,
    )
    if time_spent is not None:
        setattr(data.submission, data.model_field, time_spent)


def apply_problems_comments_field(field_data):
    if field_data.course.homework_problems_comments_field:
        field_data.submission.problems_comments = (
            field_data.request.POST.get(
                "problems_comments",
                "",
            ).strip()
        )


def apply_faq_contribution_field(field_data):
    if field_data.homework.faq_contribution_field:
        posted_url = field_data.request.POST.get("faq_contribution_url", "")
        faq_contribution_url = clean_faq_contribution_url(posted_url)
        field_data.submission.faq_contribution_url = (
            faq_contribution_url.strip()
        )


def homework_answers_from_post(request):
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


def homework_submission_for_user(user, course, homework, submission):
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


def save_homework_answers(submission, questions, answers_dict):
    for question in questions:
        answer_text = answers_dict.get(f"answer_{question.id}")
        Answer.objects.update_or_create(
            submission=submission,
            question=question,
            defaults={"answer_text": answer_text},
        )


def register_homework_submission_callbacks(data, submission):
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
    email_callback = partial(
        send_homework_confirmation_email,
        confirmation_data,
    )
    sync_callback = partial(
        sync_homework_submission_to_datamailer,
        submission,
    )
    transaction.on_commit(email_callback)
    transaction.on_commit(sync_callback)


def homework_submission_success_response(request, course, homework):
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
    response = redirect(
        "homework",
        course_slug=course.slug,
        homework_slug=homework.slug,
    )
    return response


def save_homework_submission_data(data):
    user = data.request.user
    answers_dict = homework_answers_from_post(data.request)
    submission = homework_submission_for_user(
        user,
        data.course,
        data.homework,
        data.submission,
    )
    save_homework_answers(submission, data.questions, answers_dict)
    field_data = HomeworkSubmissionFieldData(
        submission=submission,
        request=data.request,
        course=data.course,
        homework=data.homework,
        user=user,
    )
    apply_homework_submission_fields(field_data)
    submission.full_clean()
    submission.save()
    return submission


def process_homework_submission(data: HomeworkPostData):
    submission = save_homework_submission_data(data)
    register_homework_submission_callbacks(data, submission)
    return homework_submission_success_response(
        data.request,
        data.course,
        data.homework,
    )
