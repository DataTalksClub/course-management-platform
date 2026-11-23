"""Send-once staff API core shared by homework and project score emails.

The cadmin "Notify scores" buttons queue an outbox event keyed
``homework-score:<course>:<hw>`` / ``project-score:<course>:<project>``.
The staff API claims a recipient-list send audit under the same key, so a
cadmin click and an API call can never both send.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone

from api.views.project_peer_review_notifications import send_audit_to_dict
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


@dataclass(frozen=True)
class ScoreNotificationTarget:
    idempotency_key: str
    event_type: str
    template_key: str
    audit_event: str
    code_prefix: str
    label: str
    queue: Callable[[], Any]
    body_fields: dict = field(default_factory=dict)


def score_notification_send_audit(target):
    return DatamailerSendAudit.objects.filter(
        send_type=DatamailerSendAuditType.RECIPIENT_LIST,
        idempotency_key=target.idempotency_key,
    ).first()


def notification_body(target, audit, *, lookup_skips=False):
    sent = (
        audit is not None
        and audit.status == DatamailerSendAuditStatus.SUCCEEDED
    )
    return {
        **target.body_fields,
        "idempotency_key": target.idempotency_key,
        "sent": sent,
        "audit": send_audit_to_dict(audit, lookup_skips=lookup_skips),
    }


def score_notification_status_response(target):
    audit = score_notification_send_audit(target)
    return JsonResponse(
        notification_body(target, audit, lookup_skips=True)
    )


def _outbox_events(target):
    return DatamailerOutboxEvent.objects.filter(
        event_type=target.event_type,
        idempotency_key=target.idempotency_key,
    )


def _audit_defaults(target, *, status, error="", event=None):
    succeeded = (
        event is not None and status == DatamailerSendAuditStatus.SUCCEEDED
    )
    return {
        "status": status,
        "template_key": target.template_key,
        "source": "course-management-platform",
        "event": target.audit_event,
        "error": error,
        "occurred_at": (
            event.acked_at or event.occurred_at
            if succeeded
            else timezone.now()
        ),
        "enqueued_count": (
            (event.response_payload or {}).get("enqueued_count", 0)
            if succeeded
            else 0
        ),
        "response_payload": (
            event.response_payload or {} if succeeded else {}
        ),
    }


def _audit_from_outbox_event(target, event):
    """Adopt a cadmin-queued event into the shared send-once audit key."""
    if event.status == DatamailerOutboxStatus.ACKED:
        status = DatamailerSendAuditStatus.SUCCEEDED
    else:
        status = DatamailerSendAuditStatus.PENDING
    audit, created = DatamailerSendAudit.objects.get_or_create(
        send_type=DatamailerSendAuditType.RECIPIENT_LIST,
        idempotency_key=event.idempotency_key,
        defaults=_audit_defaults(target, status=status, event=event),
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
                target,
                status=DatamailerSendAuditStatus.PENDING,
                event=event,
            ),
            updated_at=now,
        )
        audit.refresh_from_db()
    return audit


def _mark_claim_failed(audit, error):
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


def _claim_failed_audit(target, audit, now):
    """Move a FAILED audit back to PENDING; only one caller can win."""
    claimed = DatamailerSendAudit.objects.filter(
        pk=audit.pk,
        status=DatamailerSendAuditStatus.FAILED,
    ).update(
        **_audit_defaults(target, status=DatamailerSendAuditStatus.PENDING),
        updated_at=now,
    )
    audit.refresh_from_db()
    return bool(claimed)


def _queue_score_notification_once(target):
    """Claim the existing audit key and enqueue score notifications once."""
    with transaction.atomic():
        audit = DatamailerSendAudit.objects.select_for_update().filter(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            idempotency_key=target.idempotency_key,
        ).first()

        if audit is not None and audit.status in (
            DatamailerSendAuditStatus.SUCCEEDED,
            DatamailerSendAuditStatus.PENDING,
        ):
            return audit, "already_queued"

        acknowledged_event = _outbox_events(target).filter(
            status=DatamailerOutboxStatus.ACKED,
        ).order_by("-created_at", "-id").first()
        if acknowledged_event is not None:
            audit = _audit_from_outbox_event(target, acknowledged_event)
            if audit.status != DatamailerSendAuditStatus.SUCCEEDED:
                DatamailerSendAudit.objects.filter(pk=audit.pk).update(
                    **_audit_defaults(
                        target,
                        status=DatamailerSendAuditStatus.SUCCEEDED,
                        event=acknowledged_event,
                    ),
                    updated_at=timezone.now(),
                )
                audit.refresh_from_db()
            return audit, "already_queued"

        active_event = _outbox_events(target).filter(
            status__in=ACTIVE_OUTBOX_STATUSES,
        ).order_by("-created_at", "-id").first()
        if active_event is not None:
            audit = _audit_from_outbox_event(target, active_event)
            return audit, "already_queued"

        now = timezone.now()
        if audit is not None:
            # A failed attempt may be retried. A conditional update means
            # concurrent retry requests can claim this row only once.
            if not _claim_failed_audit(target, audit, now):
                return audit, "already_queued"
        else:
            audit, created = DatamailerSendAudit.objects.get_or_create(
                send_type=DatamailerSendAuditType.RECIPIENT_LIST,
                idempotency_key=target.idempotency_key,
                defaults=_audit_defaults(
                    target,
                    status=DatamailerSendAuditStatus.PENDING,
                ),
            )
            if not created:
                if audit.status != DatamailerSendAuditStatus.FAILED:
                    return audit, "already_queued"
                if not _claim_failed_audit(target, audit, now):
                    return audit, "already_queued"

        # Enqueue under the same transaction as the claim so a process crash
        # cannot leave a permanent pending marker with no outbox event.
        try:
            with transaction.atomic():
                event = target.queue()
        except Exception as exc:
            error = f"Queue raised {type(exc).__name__}: {exc}"
            return _mark_claim_failed(audit, error), "failed"

        if event is None:
            audit = _mark_claim_failed(
                audit,
                "Queue finished without creating an outbox event",
            )
            return audit, "failed"
        if event.status in (
            DatamailerOutboxStatus.FAILED,
            DatamailerOutboxStatus.DEAD,
        ):
            audit = _mark_claim_failed(
                audit,
                event.last_error or "Score notification queue failed",
            )
            return audit, "failed"
        return audit, "queued"


def score_notification_send_response(target):
    failed_code = f"{target.code_prefix}_failed"
    failed_error = f"{target.label} score notification queue failed"
    try:
        audit, result = _queue_score_notification_once(target)
    except Exception as exc:
        audit = score_notification_send_audit(target)
        error = f"Queue raised {type(exc).__name__}: {exc}"
        if (
            audit is not None
            and audit.status == DatamailerSendAuditStatus.PENDING
        ):
            audit = _mark_claim_failed(audit, error)
        body = notification_body(target, audit)
        body["error"] = failed_error
        body["code"] = failed_code
        return JsonResponse(body, status=502)

    body = notification_body(target, audit)
    if result == "already_queued":
        body["error"] = (
            f"{target.label} score notification already sent or queued"
        )
        body["code"] = f"{target.code_prefix}_already_queued"
        return JsonResponse(body, status=409)
    if result == "failed":
        body["error"] = failed_error
        body["code"] = failed_code
        return JsonResponse(body, status=502)
    return JsonResponse(body)
