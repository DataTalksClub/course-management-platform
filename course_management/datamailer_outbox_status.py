from typing import Any

from django.utils import timezone

from course_management.datamailer_outbox import RETRYABLE_STATUSES
from data.models import (
    DatamailerOutboxDispatchRun,
    DatamailerOutboxDispatchRunStatus,
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
)


def datamailer_outbox_status_summary() -> dict[str, Any]:
    now = timezone.now()
    due_events = DatamailerOutboxEvent.objects.filter(
        status__in=RETRYABLE_STATUSES,
        next_attempt_at__lte=now,
    )
    event_counts = outbox_event_counts()
    due_count = due_events.count()
    ordered_due_events = due_events.order_by(
        "next_attempt_at", "created_at", "id"
    )
    oldest_due = ordered_due_events.first()
    last_successful_run = DatamailerOutboxDispatchRun.objects.filter(
        status=DatamailerOutboxDispatchRunStatus.SUCCESS,
    ).first()
    last_run = DatamailerOutboxDispatchRun.objects.first()
    last_error_events = DatamailerOutboxEvent.objects.exclude(last_error="")
    ordered_last_error_events = last_error_events.order_by(
        "-last_attempt_at", "-updated_at", "-id"
    )
    last_error_event = ordered_last_error_events.first()
    return {
        "event_counts": event_counts,
        "due_count": due_count,
        "oldest_due": oldest_due,
        "last_successful_run": last_successful_run,
        "last_run": last_run,
        "last_error_event": last_error_event,
    }


def outbox_event_counts():
    event_counts = {}
    for status in DatamailerOutboxStatus.values:
        count = DatamailerOutboxEvent.objects.filter(status=status).count()
        event_counts[status] = count
    return event_counts
