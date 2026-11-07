"""Staff API for queueing a project's score notification emails."""

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone

from api.safety import error_response
from api.views.project_peer_review_notifications import send_audit_to_dict
from course_management import email_templates
from course_management.datamailer.sync.score_notifications import (
    queue_project_score_notification,
)
from courses.models.project import ProjectState
from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)


ACTIVE_OUTBOX_STATUSES = (
    DatamailerOutboxStatus.PENDING,
    DatamailerOutboxStatus.PROCESSING,
    DatamailerOutboxStatus.RETRYING,
)


def project_score_notification_idempotency_key(project):
    return f"project-score:{project.course.slug}:{project.slug}"


def project_score_notification_send_audit(project):
    return DatamailerSendAudit.objects.filter(
        send_type=DatamailerSendAuditType.RECIPIENT_LIST,
        idempotency_key=project_score_notification_idempotency_key(project),
    ).first()


def _notification_body(project, audit, *, lookup_skips=False):
    sent = (
        audit is not None
        and audit.status == DatamailerSendAuditStatus.SUCCEEDED
    )
    return {
        "course_slug": project.course.slug,
        "project_slug": project.slug,
        "idempotency_key": project_score_notification_idempotency_key(
            project
        ),
        "sent": sent,
        "audit": send_audit_to_dict(audit, lookup_skips=lookup_skips),
    }


def project_score_notification_status_response(project):
    audit = project_score_notification_send_audit(project)
    return JsonResponse(
        _notification_body(project, audit, lookup_skips=True)
    )


def _outbox_events(project):
    return DatamailerOutboxEvent.objects.filter(
        event_type="project.score_notification",
        idempotency_key=project_score_notification_idempotency_key(project),
    )


def _audit_defaults(project, *, status, error="", event=None):
    return {
        "status": status,
        "template_key": email_templates.PROJECT_SCORE_NOTIFICATION,
        "source": "course-management-platform",
        "event": "project_score_notification",
        "error": error,
        "occurred_at": (
            event.acked_at or event.occurred_at
            if event is not None
            and status == DatamailerSendAuditStatus.SUCCEEDED
            else timezone.now()
        ),
        "enqueued_count": (
            (event.response_payload or {}).get("enqueued_count", 0)
            if event is not None and status == DatamailerSendAuditStatus.SUCCEEDED
            else 0
        ),
        "response_payload": (
            event.response_payload or {}
            if event is not None and status == DatamailerSendAuditStatus.SUCCEEDED
            else {}
        ),
    }


def _audit_from_outbox_event(project, event):
    """Adopt a cadmin-queued event into the shared send-once audit key."""
    if event.status == DatamailerOutboxStatus.ACKED:
        status = DatamailerSendAuditStatus.SUCCEEDED
    else:
        status = DatamailerSendAuditStatus.PENDING
    audit, created = DatamailerSendAudit.objects.get_or_create(
        send_type=DatamailerSendAuditType.RECIPIENT_LIST,
        idempotency_key=event.idempotency_key,
        defaults=_audit_defaults(project, status=status, event=event),
    )
    if (
        not created
        and audit.status == DatamailerSendAuditStatus.FAILED
        and event.status != DatamailerOutboxStatus.ACKED
        and event.created_at > audit.updated_at
    ):
        now = timezone.now()
        DatamailerSendAudit.objects.filter(
            pk=audit.pk,
            status=DatamailerSendAuditStatus.FAILED,
        ).update(
            **_audit_defaults(
                project,
                status=DatamailerSendAuditStatus.PENDING,
                event=event,
            ),
            updated_at=now,
        )
        audit.refresh_from_db()
    return audit


def _mark_claim_failed(project, audit, error):
    now = timezone.now()
    DatamailerSendAudit.objects.filter(
        pk=audit.pk,
        status=DatamailerSendAuditStatus.PENDING,
    ).update(
        status=DatamailerSendAuditStatus.FAILED,
        error=error,
        updated_at=now,
    )
    audit.refresh_from_db()
    return audit


def _queue_project_score_notification_once(project):
    """Claim the existing audit key and enqueue score notifications once."""
    key = project_score_notification_idempotency_key(project)
    with transaction.atomic():
        audit = DatamailerSendAudit.objects.select_for_update().filter(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            idempotency_key=key,
        ).first()

        if audit is not None and audit.status in (
            DatamailerSendAuditStatus.SUCCEEDED,
            DatamailerSendAuditStatus.PENDING,
        ):
            return audit, "already_queued"

        acknowledged_event = _outbox_events(project).filter(
            status=DatamailerOutboxStatus.ACKED,
        ).order_by("-created_at", "-id").first()
        if acknowledged_event is not None:
            audit = _audit_from_outbox_event(project, acknowledged_event)
            if audit.status != DatamailerSendAuditStatus.SUCCEEDED:
                DatamailerSendAudit.objects.filter(pk=audit.pk).update(
                    **_audit_defaults(
                        project,
                        status=DatamailerSendAuditStatus.SUCCEEDED,
                        event=acknowledged_event,
                    ),
                    updated_at=timezone.now(),
                )
                audit.refresh_from_db()
            return audit, "already_queued"

        active_event = _outbox_events(project).filter(
            status__in=ACTIVE_OUTBOX_STATUSES,
        ).order_by("-created_at", "-id").first()
        if active_event is not None:
            audit = _audit_from_outbox_event(project, active_event)
            return audit, "already_queued"

        now = timezone.now()
        if audit is not None:
            # A failed attempt may be retried. A conditional update means
            # concurrent retry requests can claim this row only once.
            claimed = DatamailerSendAudit.objects.filter(
                pk=audit.pk,
                status=DatamailerSendAuditStatus.FAILED,
            ).update(
                **_audit_defaults(
                    project,
                    status=DatamailerSendAuditStatus.PENDING,
                ),
                updated_at=now,
            )
            if not claimed:
                audit.refresh_from_db()
                return audit, "already_queued"
            audit.refresh_from_db()
        else:
            audit, created = DatamailerSendAudit.objects.get_or_create(
                send_type=DatamailerSendAuditType.RECIPIENT_LIST,
                idempotency_key=key,
                defaults=_audit_defaults(
                    project,
                    status=DatamailerSendAuditStatus.PENDING,
                ),
            )
            if not created:
                if audit.status != DatamailerSendAuditStatus.FAILED:
                    return audit, "already_queued"
                claimed = DatamailerSendAudit.objects.filter(
                    pk=audit.pk,
                    status=DatamailerSendAuditStatus.FAILED,
                ).update(
                    **_audit_defaults(
                        project,
                        status=DatamailerSendAuditStatus.PENDING,
                    ),
                    updated_at=now,
                )
                if not claimed:
                    audit.refresh_from_db()
                    return audit, "already_queued"
                audit.refresh_from_db()

        # Enqueue under the same transaction as the claim so a process crash
        # cannot leave a permanent pending marker with no outbox event.
        try:
            with transaction.atomic():
                event = queue_project_score_notification(project)
        except Exception as exc:
            error = f"Queue raised {type(exc).__name__}: {exc}"
            audit = _mark_claim_failed(project, audit, error)
            return audit, "failed"

        if event is None:
            audit = _mark_claim_failed(
                project,
                audit,
                "Queue finished without creating an outbox event",
            )
            return audit, "failed"
        if event.status in (
            DatamailerOutboxStatus.FAILED,
            DatamailerOutboxStatus.DEAD,
        ):
            audit = _mark_claim_failed(
                project,
                audit,
                event.last_error or "Score notification queue failed",
            )
            return audit, "failed"
        return audit, "queued"


def project_score_notification_send_response(project):
    if project.state != ProjectState.COMPLETED.value:
        return error_response(
            "Score the project before notifying students",
            "project_not_completed",
            details={"state": project.state},
        )

    try:
        audit, result = _queue_project_score_notification_once(project)
    except Exception as exc:
        audit = project_score_notification_send_audit(project)
        error = f"Queue raised {type(exc).__name__}: {exc}"
        if audit is not None and audit.status == DatamailerSendAuditStatus.PENDING:
            audit = _mark_claim_failed(project, audit, error)
        body = _notification_body(project, audit)
        body["error"] = "Project score notification queue failed"
        body["code"] = "project_score_notification_failed"
        return JsonResponse(body, status=502)

    body = _notification_body(project, audit)
    if result == "already_queued":
        body["error"] = "Project score notification already sent or queued"
        body["code"] = "project_score_notification_already_queued"
        return JsonResponse(body, status=409)
    if result == "failed":
        body["error"] = "Project score notification queue failed"
        body["code"] = "project_score_notification_failed"
        return JsonResponse(body, status=502)
    return JsonResponse(body)
