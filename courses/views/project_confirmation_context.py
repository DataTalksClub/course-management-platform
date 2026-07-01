from dataclasses import dataclass

from courses.models.course import Course
from courses.models.project import Project, ProjectSubmission
from courses.views.project_confirmation_fields import project_submission_fields
from courses.views.submission_formatting import format_submission_lines


@dataclass(frozen=True)
class ProjectConfirmationData:
    course: Course
    project: Project
    submission: ProjectSubmission
    update_url: str
    profile_url: str


def project_confirmation_metadata(
    data: ProjectConfirmationData,
) -> dict:
    project_due_at = data.project.submission_due_date.isoformat()
    submitted_at = data.submission.submitted_at.isoformat()
    return {
        "course_slug": data.course.slug,
        "course_title": data.course.title,
        "project_slug": data.project.slug,
        "project_title": data.project.title,
        "project_due_at": project_due_at,
        "submission_id": data.submission.id,
        "submitted_at": submitted_at,
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
    metadata = project_confirmation_metadata(data)
    notification_context = project_confirmation_notification_context(
        data.profile_url
    )
    message_context = project_confirmation_message_context(data)

    context = {}
    context.update(metadata)
    context.update(notification_context)
    context.update(message_context)
    context["submission_fields"] = submission_fields
    context["submitted_fields_text"] = submitted_fields_text
    context["submission_summary_text"] = submitted_fields_text
    return context
