from dataclasses import dataclass
from typing import Any

from django.http import HttpRequest
from django.urls import reverse

from course_management import email_templates
from course_management.datamailer.sync import send_transactional_email
from courses.models import Course, Homework, Submission, User
from courses.views.homework_submission_summary import (
    homework_submitted_content,
)
from courses.views.submission_formatting import (
    build_account_settings_url,
    request_base_url,
)
from courses.views.url_utils import absolute_url_with_fallback


@dataclass(frozen=True)
class HomeworkConfirmationEmailData:
    user: User
    course: Course
    homework: Homework
    submission: Submission
    update_url: str


@dataclass(frozen=True)
class HomeworkConfirmationData:
    course: Course
    homework: Homework
    submission: Submission
    update_url: str
    profile_url: str


def homework_confirmation_metadata(
    data: HomeworkConfirmationData,
) -> dict[str, Any]:
    return {
        "course_slug": data.course.slug,
        "course_title": data.course.title,
        "homework_slug": data.homework.slug,
        "homework_title": data.homework.title,
        "homework_due_at": data.homework.due_date.isoformat(),
        "submission_id": data.submission.id,
        "submitted_at": data.submission.submitted_at.isoformat(),
        "update_url": data.update_url,
        "profile_url": data.profile_url,
        "update_link_text": "Update your submission",
    }


def homework_confirmation_notification_context(
    profile_url: str,
) -> dict[str, str]:
    return {
        "notification_category": "homework and project submissions",
        "notification_footer": (
            "You are receiving this because homework and project "
            "submission emails are enabled in your profile."
        ),
        "notification_footer_text": (
            "If you don't want to receive these emails, you can turn "
            "off homework and project submission emails in your "
            f"profile: {profile_url}"
        ),
    }


def homework_confirmation_message_context(
    data: HomeworkConfirmationData,
) -> dict[str, str]:
    return {
        "email_subject": (
            f"Homework submission saved: {data.homework.title}"
        ),
        "email_preview": (
            "Your homework submission was saved. "
            "Review what you submitted and update it while the "
            "homework is open."
        ),
        "intro_text": (
            f"Your homework submission for {data.homework.title} in "
            f"{data.course.title} was saved."
        ),
        "update_text": (
            "You can update your submission while the homework "
            f"is open: {data.update_url}"
        ),
    }


def homework_confirmation_context(
    data: HomeworkConfirmationData,
) -> dict[str, Any]:
    submitted_content = homework_submitted_content(
        data.course,
        data.homework,
        data.submission,
    )

    return {
        **homework_confirmation_metadata(data),
        **homework_confirmation_notification_context(data.profile_url),
        **homework_confirmation_message_context(data),
        **submitted_content.context(),
    }


def build_homework_update_url(
    request: HttpRequest,
    course: Course,
    homework: Homework,
) -> str:
    path = reverse(
        "homework",
        kwargs={
            "course_slug": course.slug,
            "homework_slug": homework.slug,
        },
    )
    return absolute_url_with_fallback(request, path, label="homework")


def send_homework_confirmation_email(data: HomeworkConfirmationEmailData) -> None:
    if not data.user.email:
        return

    payload = homework_confirmation_payload(data)
    send_transactional_email(payload)


def homework_confirmation_payload(data: HomeworkConfirmationEmailData) -> dict:
    return {
        "email": data.user.email,
        "template_key": email_templates.HOMEWORK_SUBMISSION_CONFIRMATION,
        "category_tag": "submission-results",
        "idempotency_key": homework_confirmation_idempotency_key(
            data.submission
        ),
        "context": homework_confirmation_payload_context(data),
        "metadata": homework_confirmation_email_metadata(data),
    }


def homework_confirmation_payload_context(
    data: HomeworkConfirmationEmailData,
) -> dict[str, Any]:
    base_url = request_base_url(data.update_url)
    profile_url = build_account_settings_url(base_url)
    context_data = HomeworkConfirmationData(
        course=data.course,
        homework=data.homework,
        submission=data.submission,
        update_url=data.update_url,
        profile_url=profile_url,
    )
    return homework_confirmation_context(context_data)


def homework_confirmation_idempotency_key(submission: Submission) -> str:
    return (
        f"homework-submission:{submission.id}:"
        f"{submission.submitted_at.isoformat()}"
    )


def homework_confirmation_email_metadata(
    data: HomeworkConfirmationEmailData,
) -> dict:
    return {
        "source": "course-management-platform",
        "event": "homework_submission",
        "course_slug": data.course.slug,
        "homework_slug": data.homework.slug,
        "submission_id": data.submission.id,
    }
