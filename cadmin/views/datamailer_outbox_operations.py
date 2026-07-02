from django.utils import timezone

from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
)

REQUEUEABLE_OUTBOX_STATUSES = (
    DatamailerOutboxStatus.FAILED,
    DatamailerOutboxStatus.DEAD,
)

FAILED_OUTBOX_STATUSES = (
    DatamailerOutboxStatus.RETRYING,
    DatamailerOutboxStatus.FAILED,
    DatamailerOutboxStatus.DEAD,
)


def requeue_datamailer_outbox_events():
    now = timezone.now()
    requeued_count = DatamailerOutboxEvent.objects.filter(
        status__in=REQUEUEABLE_OUTBOX_STATUSES,
    ).update(
        status=DatamailerOutboxStatus.RETRYING,
        next_attempt_at=now,
        last_error="",
        updated_at=now,
    )
    return requeued_count


def recent_failed_datamailer_outbox_events():
    events = DatamailerOutboxEvent.objects.filter(
        status__in=FAILED_OUTBOX_STATUSES,
    ).exclude(last_error="")[:10]
    return events


def datamailer_outbox_status_rows(outbox_summary):
    rows = []
    event_counts = outbox_summary["event_counts"]

    for status in DatamailerOutboxStatus.values:
        count = event_counts.get(status, 0)
        row = {
            "status": status,
            "count": count,
        }
        rows.append(row)
    return rows
