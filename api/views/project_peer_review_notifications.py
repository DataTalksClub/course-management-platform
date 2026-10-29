from django.http import JsonResponse

from api.safety import error_response
from course_management.datamailer.sync.peer_review_send_once import (
    PeerReviewNotificationAlreadySent,
    peer_review_assignment_idempotency_key,
    peer_review_assignment_send_audit,
    send_peer_review_assignment_notification_once,
)
from courses.models.project import ProjectState
from data.models import DatamailerSendAuditStatus


def _isoformat(value):
    if value is None:
        return None
    return value.isoformat()


def send_audit_to_dict(audit):
    if audit is None:
        return None
    return {
        "send_type": audit.send_type,
        "status": audit.status,
        "idempotency_key": audit.idempotency_key,
        "template_key": audit.template_key,
        "list_key": audit.list_key,
        "intended_count": audit.intended_count,
        "created_count": audit.created_count,
        "enqueued_count": audit.enqueued_count,
        "skipped_count": audit.skipped_count,
        "idempotent_replay_count": audit.idempotent_replay_count,
        "error": audit.error,
        "occurred_at": _isoformat(audit.occurred_at),
        "created_at": _isoformat(audit.created_at),
        "updated_at": _isoformat(audit.updated_at),
    }


def _notification_body(project, audit):
    sent = (
        audit is not None
        and audit.status == DatamailerSendAuditStatus.SUCCEEDED
    )
    return {
        "course_slug": project.course.slug,
        "project_slug": project.slug,
        "idempotency_key": peer_review_assignment_idempotency_key(project),
        "sent": sent,
        "audit": send_audit_to_dict(audit),
    }


def peer_review_notification_status_response(project):
    audit = peer_review_assignment_send_audit(project)
    return JsonResponse(_notification_body(project, audit))


def peer_review_notification_send_response(request, project):
    if project.state != ProjectState.PEER_REVIEWING.value:
        return error_response(
            "Assign peer reviews before notifying students",
            "project_not_peer_reviewing",
            details={"state": project.state},
        )
    try:
        audit = send_peer_review_assignment_notification_once(project)
    except PeerReviewNotificationAlreadySent as exc:
        body = _notification_body(project, exc.audit)
        body["error"] = (
            "Peer review notification already sent or in progress"
        )
        body["code"] = "peer_review_notification_already_sent"
        return JsonResponse(body, status=409)

    body = _notification_body(project, audit)
    if audit.status != DatamailerSendAuditStatus.SUCCEEDED:
        body["error"] = "Peer review notification send failed"
        body["code"] = "peer_review_notification_failed"
        return JsonResponse(body, status=502)
    return JsonResponse(body)
