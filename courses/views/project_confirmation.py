from dataclasses import dataclass

from django.http import HttpRequest
from django.urls import reverse

from course_management import email_templates
from course_management.datamailer.sync.transactional import (
    send_transactional_email,
)
from courses.models import Course, Project, ProjectSubmission, User
from courses.views.project_confirmation_context import (
    ProjectConfirmationData,
    project_confirmation_context,
)
from courses.views.submission_formatting import (
    build_account_settings_url,
    request_base_url,
)
from courses.views.url_utils import absolute_url_with_fallback


@dataclass(frozen=True)
class ProjectConfirmationEmailData:
    user: User
    course: Course
    project: Project
    submission: ProjectSubmission
    update_url: str


def build_project_update_url(
    request: HttpRequest,
    course: Course,
    project: Project,
) -> str:
    path = reverse(
        "project",
        kwargs={
            "course_slug": course.slug,
            "project_slug": project.slug,
        },
    )
    return absolute_url_with_fallback(request, path, label="project")


def send_project_confirmation_email(data: ProjectConfirmationEmailData) -> None:
    if not data.user.email:
        return

    payload = project_confirmation_payload(data)
    send_transactional_email(payload)


def project_confirmation_payload(data: ProjectConfirmationEmailData) -> dict:
    idempotency_key = project_confirmation_idempotency_key(data.submission)
    context = project_confirmation_payload_context(data)
    metadata = project_confirmation_email_metadata(data)
    return {
        "email": data.user.email,
        "template_key": email_templates.PROJECT_SUBMISSION_CONFIRMATION,
        "category_tag": "submission-results",
        "idempotency_key": idempotency_key,
        "context": context,
        "metadata": metadata,
    }


def project_confirmation_payload_context(
    data: ProjectConfirmationEmailData,
) -> dict:
    base_url = request_base_url(data.update_url)
    profile_url = build_account_settings_url(base_url)
    context_data = ProjectConfirmationData(
        course=data.course,
        project=data.project,
        submission=data.submission,
        update_url=data.update_url,
        profile_url=profile_url,
    )
    context = project_confirmation_context(context_data)
    return context


def project_confirmation_idempotency_key(
    submission: ProjectSubmission,
) -> str:
    return (
        f"project-submission:{submission.id}:"
        f"{submission.submitted_at.isoformat()}"
    )


def project_confirmation_email_metadata(
    data: ProjectConfirmationEmailData,
) -> dict:
    return {
        "source": "course-management-platform",
        "event": "project_submission",
        "course_slug": data.course.slug,
        "project_slug": data.project.slug,
        "submission_id": data.submission.id,
    }
