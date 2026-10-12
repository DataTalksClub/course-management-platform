from dataclasses import dataclass

from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
)


@dataclass(frozen=True)
class ScoreNotificationStatus:
    state: str  # "not_queued", "pending", "succeeded", "retrying", "failed", "dead"
    message: str
    error: str = ""
    enqueued_count: int = 0
    attempt_count: int = 0
    is_failed_or_retrying: bool = False
    is_succeeded: bool = False
    is_pending: bool = False


def get_score_notification_status(idempotency_key: str) -> ScoreNotificationStatus:
    """Evaluate current delivery state of a score notification from outbox and audits."""
    audit = (
        DatamailerSendAudit.objects.filter(idempotency_key=idempotency_key)
        .order_by("-occurred_at", "-id")
        .first()
    )
    outbox_event = (
        DatamailerOutboxEvent.objects.filter(idempotency_key=idempotency_key)
        .order_by("-created_at", "-id")
        .first()
    )

    bulk_upsert_key = (
        f"recipient-list.members-bulk-upsert:{idempotency_key}:members"
    )
    bulk_upsert_event = (
        DatamailerOutboxEvent.objects.filter(idempotency_key=bulk_upsert_key)
        .order_by("-created_at", "-id")
        .first()
    )

    if not outbox_event and not audit:
        return ScoreNotificationStatus(
            state="not_queued",
            message="",
        )

    # Succeeded state
    if (audit and audit.status == DatamailerSendAuditStatus.SUCCEEDED) or (
        outbox_event and outbox_event.status == DatamailerOutboxStatus.ACKED
    ):
        enqueued_count = audit.enqueued_count if audit else 0
        return ScoreNotificationStatus(
            state="succeeded",
            message=f"Score notifications sent: {enqueued_count} emails delivered via Relay.",
            enqueued_count=enqueued_count,
            is_succeeded=True,
        )

    # Check for failing/retrying states
    is_outbox_failing = outbox_event and outbox_event.status in (
        DatamailerOutboxStatus.RETRYING,
        DatamailerOutboxStatus.FAILED,
        DatamailerOutboxStatus.DEAD,
    )
    is_audit_failing = (
        audit and audit.status == DatamailerSendAuditStatus.FAILED
    )
    is_bulk_failing = bulk_upsert_event and bulk_upsert_event.status in (
        DatamailerOutboxStatus.RETRYING,
        DatamailerOutboxStatus.FAILED,
        DatamailerOutboxStatus.DEAD,
    )

    if is_outbox_failing or is_audit_failing or is_bulk_failing:
        error = ""
        if bulk_upsert_event and bulk_upsert_event.last_error:
            error = bulk_upsert_event.last_error
        elif outbox_event and outbox_event.last_error:
            error = outbox_event.last_error
        elif audit and audit.error:
            error = audit.error
        else:
            error = "Relay rejected or failed the request"

        attempts = outbox_event.attempt_count if outbox_event else 1
        state = "retrying"
        if outbox_event and outbox_event.status in (
            DatamailerOutboxStatus.FAILED,
            DatamailerOutboxStatus.DEAD,
        ):
            state = outbox_event.status
            msg = (
                f"Score notifications could not be delivered: "
                f"Relay is unavailable or rejected the send ({error}). Delivery failed."
            )
        else:
            msg = (
                f"Score notifications could not be delivered: "
                f"Relay is unavailable or rejected the send ({error}). "
                "Delivery is retrying automatically."
            )

        return ScoreNotificationStatus(
            state=state,
            message=msg,
            error=error,
            attempt_count=attempts,
            is_failed_or_retrying=True,
        )

    # Pending or processing
    return ScoreNotificationStatus(
        state="pending",
        message="Score notifications are queued for delivery.",
        is_pending=True,
    )


def get_homework_score_notification_status(
    homework,
) -> ScoreNotificationStatus:
    idempotency_key = f"homework-score:{homework.course.slug}:{homework.slug}"
    return get_score_notification_status(idempotency_key)


def get_project_score_notification_status(
    project,
) -> ScoreNotificationStatus:
    idempotency_key = f"project-score:{project.course.slug}:{project.slug}"
    return get_score_notification_status(idempotency_key)
