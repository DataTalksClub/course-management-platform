"""Staff API for queueing a homework's score notification emails.

Mirrors cadmin ``homework_notify_scores`` and shares its send key
``homework-score:<course>:<homework>``, so a homework already notified from
cadmin (or by a previous API call) is never sent again.
"""

from api.safety import error_response
from api.views.score_notification_send import (
    ScoreNotificationTarget,
    score_notification_send_response,
    score_notification_status_response,
)
from course_management import email_templates
from course_management.datamailer.sync.score_notifications import (
    queue_homework_score_notification,
)


def homework_score_notification_idempotency_key(homework):
    return f"homework-score:{homework.course.slug}:{homework.slug}"


def homework_score_notification_target(homework):
    return ScoreNotificationTarget(
        idempotency_key=homework_score_notification_idempotency_key(
            homework
        ),
        event_type="homework.score_notification",
        template_key=email_templates.HOMEWORK_SCORE_NOTIFICATION,
        audit_event="homework_score_notification",
        code_prefix="homework_score_notification",
        label="Homework",
        # Late-bound so tests can patch the module-level queue function.
        queue=lambda: queue_homework_score_notification(homework),
        body_fields={
            "course_slug": homework.course.slug,
            "homework_slug": homework.slug,
        },
    )


def homework_score_notification_status_response(homework):
    target = homework_score_notification_target(homework)
    return score_notification_status_response(target)


def homework_score_notification_send_response(homework):
    if not homework.is_scored():
        return error_response(
            "Score the homework before notifying students",
            "homework_not_scored",
            details={"state": homework.state},
        )
    target = homework_score_notification_target(homework)
    return score_notification_send_response(target)
