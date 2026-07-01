from django.utils import timezone

from course_management.datamailer_outbox import RETRYABLE_STATUSES
from course_management.datamailer_outbox_dispatch import (
    dispatch_datamailer_outbox_event,
)
from data.models import (
    DatamailerOutboxDispatchRun,
    DatamailerOutboxDispatchRunStatus,
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
)


def process_due_datamailer_outbox(
    *, limit=100, record_run=True
) -> dict[str, int]:
    started_at = timezone.now()
    run = None
    if record_run:
        run = DatamailerOutboxDispatchRun.objects.create(
            started_at=started_at,
            status=DatamailerOutboxDispatchRunStatus.SUCCESS,
        )
    event_ids = due_outbox_event_ids(limit)
    counts = {
        "processed": 0,
        "acked": 0,
        "retrying": 0,
        "failed": 0,
    }

    try:
        process_outbox_event_ids(event_ids, counts)
    except Exception as exc:
        last_error = str(exc)
        finish_failed_dispatch_run(run, counts, last_error)
        raise

    finish_successful_dispatch_run(run, counts)
    return counts


def due_outbox_event_ids(limit):
    now = timezone.now()
    event_ids = DatamailerOutboxEvent.objects.filter(
        status__in=RETRYABLE_STATUSES,
        next_attempt_at__lte=now,
    )
    ordered_event_ids = event_ids.order_by("created_at", "id")
    due_ids = ordered_event_ids.values_list("id", flat=True)[:limit]
    result = list(due_ids)
    return result


def process_outbox_event_ids(event_ids, counts):
    for event_id in event_ids:
        event = DatamailerOutboxEvent.objects.get(id=event_id)
        dispatch_datamailer_outbox_event(event)
        event.refresh_from_db()
        count_processed_outbox_event(counts, event)


def count_processed_outbox_event(counts, event):
    counts["processed"] += 1
    counted_statuses = {
        DatamailerOutboxStatus.ACKED,
        DatamailerOutboxStatus.RETRYING,
        DatamailerOutboxStatus.FAILED,
    }
    if event.status in counted_statuses:
        counts[event.status] += 1


def finish_failed_dispatch_run(run, counts, last_error):
    finish_dispatch_run_if_present(
        run,
        counts,
        status=DatamailerOutboxDispatchRunStatus.FAILED,
        last_error=last_error,
    )


def finish_successful_dispatch_run(run, counts):
    finish_dispatch_run_if_present(
        run,
        counts,
        status=DatamailerOutboxDispatchRunStatus.SUCCESS,
        last_error="",
    )


def finish_dispatch_run_if_present(run, counts, *, status, last_error):
    if run is None:
        return

    finish_dispatch_run(
        run,
        counts,
        status=status,
        last_error=last_error,
    )


def finish_dispatch_run(run, counts, *, status, last_error):
    finished_at = timezone.now()
    run.status = status
    run.finished_at = finished_at
    run.processed_count = counts["processed"]
    run.acked_count = counts["acked"]
    run.retrying_count = counts["retrying"]
    run.failed_count = counts["failed"]
    run.last_error = last_error
    run.save(
        update_fields=[
            "status",
            "finished_at",
            "processed_count",
            "acked_count",
            "retrying_count",
            "failed_count",
            "last_error",
        ]
    )
