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
    due_events = due_outbox_events(now)
    dispatch_runs = outbox_dispatch_runs()
    event_counts = outbox_event_counts()
    due_count = due_events.count()
    oldest_due = oldest_due_outbox_event(due_events)
    last_successful_run = dispatch_runs["last_successful_run"]
    last_run = dispatch_runs["last_run"]
    last_error_event = last_error_outbox_event()
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


def due_outbox_events(now):
    return DatamailerOutboxEvent.objects.filter(
        status__in=RETRYABLE_STATUSES,
        next_attempt_at__lte=now,
    )


def oldest_due_outbox_event(due_events):
    ordered_events = due_events.order_by("next_attempt_at", "created_at", "id")
    oldest_event = ordered_events.first()
    return oldest_event


def outbox_dispatch_runs():
    last_successful_run = DatamailerOutboxDispatchRun.objects.filter(
        status=DatamailerOutboxDispatchRunStatus.SUCCESS,
    ).first()
    last_run = DatamailerOutboxDispatchRun.objects.first()
    return {
        "last_successful_run": last_successful_run,
        "last_run": last_run,
    }


def last_error_outbox_event():
    return (
        DatamailerOutboxEvent.objects.exclude(last_error="")
        .order_by("-last_attempt_at", "-updated_at", "-id")
        .first()
    )
