"""Staff API for queueing a project's score notification emails."""

from api.safety import error_response
from api.views.score_notification_send import (
    ScoreNotificationTarget,
    score_notification_send_audit,
    score_notification_send_response,
    score_notification_status_response,
)
from course_management import email_templates
from course_management.datamailer.sync.score_notifications import (
    queue_project_score_notification,
)
from courses.models.project import ProjectState


def project_score_notification_idempotency_key(project):
    return f"project-score:{project.course.slug}:{project.slug}"


def project_score_notification_target(project):
    return ScoreNotificationTarget(
        idempotency_key=project_score_notification_idempotency_key(project),
        event_type="project.score_notification",
        template_key=email_templates.PROJECT_SCORE_NOTIFICATION,
        audit_event="project_score_notification",
        code_prefix="project_score_notification",
        label="Project",
        # Late-bound so tests can patch the module-level queue function.
        queue=lambda: queue_project_score_notification(project),
        body_fields={
            "course_slug": project.course.slug,
            "project_slug": project.slug,
        },
    )


def project_score_notification_send_audit(project):
    target = project_score_notification_target(project)
    return score_notification_send_audit(target)


def project_score_notification_status_response(project):
    target = project_score_notification_target(project)
    return score_notification_status_response(target)


def project_score_notification_send_response(project):
    if project.state != ProjectState.COMPLETED.value:
        return error_response(
            "Score the project before notifying students",
            "project_not_completed",
            details={"state": project.state},
        )
    target = project_score_notification_target(project)
    return score_notification_send_response(target)
