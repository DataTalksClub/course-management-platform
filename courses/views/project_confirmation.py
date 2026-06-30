from dataclasses import dataclass

from django.http import HttpRequest
from django.urls import reverse

from course_management import email_templates
from course_management.datamailer.sync import send_transactional_email
from courses.models import Course, Project, ProjectSubmission, User
from courses.views.homework_answers import format_hours
from courses.views.submission_formatting import (
    build_account_settings_url,
    format_submission_lines,
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


@dataclass(frozen=True)
class ProjectConfirmationData:
    course: Course
    project: Project
    submission: ProjectSubmission
    update_url: str
    profile_url: str


def project_repository_submission_field(
    submission: ProjectSubmission,
) -> dict:
    return {
        "key": "github_link",
        "label": "GitHub repository",
        "value": submission.github_link or "",
    }


def project_commit_submission_field(
    submission: ProjectSubmission,
) -> dict:
    return {
        "key": "commit_id",
        "label": "Commit ID",
        "value": submission.commit_id or "",
    }


def project_learning_in_public_submission_field(
    project: Project,
    submission: ProjectSubmission,
) -> dict | None:
    if project.learning_in_public_cap_project <= 0:
        return None

    links = submission.learning_in_public_links or []
    return {
        "key": "learning_in_public_links",
        "label": "Learning in public links",
        "value": "\n".join(links),
        "values": links,
    }


def project_time_submission_field(
    project: Project,
    submission: ProjectSubmission,
) -> dict | None:
    if not project.time_spent_project_field:
        return None

    return {
        "key": "time_spent",
        "label": "Time spent on project",
        "value": format_hours(submission.time_spent),
    }


def project_problems_comments_submission_field(
    project: Project,
    submission: ProjectSubmission,
) -> dict | None:
    if not project.problems_comments_field:
        return None

    return {
        "key": "problems_comments",
        "label": "Problems, comments, or feedback",
        "value": submission.problems_comments or "",
    }


def project_faq_contribution_submission_field(
    project: Project,
    submission: ProjectSubmission,
) -> dict | None:
    if not project.faq_contribution_field:
        return None

    return {
        "key": "faq_contribution_url",
        "label": "FAQ contribution URL",
        "value": submission.faq_contribution_url or "",
    }


def project_required_submission_fields(
    submission: ProjectSubmission,
) -> list[dict]:
    fields = []
    repository_field = project_repository_submission_field(submission)
    fields.append(repository_field)
    commit_field = project_commit_submission_field(submission)
    fields.append(commit_field)
    return fields


def project_optional_submission_fields(
    project: Project,
    submission: ProjectSubmission,
) -> list[dict | None]:
    fields = []
    learning_in_public_field = project_learning_in_public_submission_field(
        project,
        submission,
    )
    fields.append(learning_in_public_field)
    time_field = project_time_submission_field(project, submission)
    fields.append(time_field)
    problems_comments_field = project_problems_comments_submission_field(
        project,
        submission,
    )
    fields.append(problems_comments_field)
    faq_contribution_field = project_faq_contribution_submission_field(
        project,
        submission,
    )
    fields.append(faq_contribution_field)
    return fields


def visible_project_submission_fields(fields: list[dict | None]) -> list[dict]:
    visible_fields = []
    for field in fields:
        if field is not None:
            visible_fields.append(field)
    return visible_fields


def project_submission_fields(
    project: Project,
    submission: ProjectSubmission,
) -> list[dict]:
    fields = []
    required_fields = project_required_submission_fields(submission)
    fields.extend(required_fields)
    optional_fields = project_optional_submission_fields(
        project,
        submission,
    )
    fields.extend(optional_fields)
    return visible_project_submission_fields(fields)


def project_confirmation_metadata(
    data: ProjectConfirmationData,
) -> dict:
    return {
        "course_slug": data.course.slug,
        "course_title": data.course.title,
        "project_slug": data.project.slug,
        "project_title": data.project.title,
        "project_due_at": data.project.submission_due_date.isoformat(),
        "submission_id": data.submission.id,
        "submitted_at": data.submission.submitted_at.isoformat(),
        "update_url": data.update_url,
        "profile_url": data.profile_url,
        "update_link_text": "Update your submission",
    }


def project_confirmation_notification_context(profile_url: str) -> dict:
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


def project_confirmation_message_context(
    data: ProjectConfirmationData,
) -> dict:
    return {
        "email_subject": f"Project submission saved: {data.project.title}",
        "email_preview": (
            "Your project submission was saved. Review what you "
            "submitted and update it while the project is open."
        ),
        "intro_text": (
            f"Your project submission for {data.project.title} in "
            f"{data.course.title} was saved."
        ),
        "update_text": (
            "You can update your submission while the project "
            f"is open: {data.update_url}"
        ),
    }


def project_confirmation_context(
    data: ProjectConfirmationData,
) -> dict:
    submission_fields = project_submission_fields(
        data.project,
        data.submission,
    )
    submitted_fields_text = format_submission_lines(submission_fields)

    return {
        **project_confirmation_metadata(data),
        **project_confirmation_notification_context(data.profile_url),
        **project_confirmation_message_context(data),
        "submission_fields": submission_fields,
        "submitted_fields_text": submitted_fields_text,
        "submission_summary_text": submitted_fields_text,
    }


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
    return {
        "email": data.user.email,
        "template_key": email_templates.PROJECT_SUBMISSION_CONFIRMATION,
        "category_tag": "submission-results",
        "idempotency_key": project_confirmation_idempotency_key(
            data.submission
        ),
        "context": project_confirmation_payload_context(data),
        "metadata": project_confirmation_email_metadata(data),
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
    return project_confirmation_context(context_data)


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
