import logging
import time
from datetime import timedelta

from django.db.models import Q
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

logger = logging.getLogger(__name__)

# Keep each minutely outbox tick well under the 300s Coolify/alarm timeout
# when pacing a large backlog.
OUTBOX_RUN_MAX_SECONDS = 45.0


def process_due_datamailer_outbox(
    *,
    limit=100,
    record_run=True,
    max_duration_seconds: float | None = OUTBOX_RUN_MAX_SECONDS,
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
        process_outbox_event_ids(
            event_ids,
            counts,
            max_duration_seconds=max_duration_seconds,
        )
    except Exception as exc:
        last_error = str(exc)
        finish_failed_dispatch_run(run, counts, last_error)
        raise

    if counts["failed"] > 0:
        logger.error(
            "Datamailer outbox dispatch run finished with %s failed event(s).",
            counts["failed"],
        )

    finish_successful_dispatch_run(run, counts)
    return counts


def due_outbox_event_ids(limit):
    now = timezone.now()
    event_ids = DatamailerOutboxEvent.objects.filter(
        Q(status__in=RETRYABLE_STATUSES, next_attempt_at__lte=now)
        | Q(status=DatamailerOutboxStatus.PROCESSING,
            last_attempt_at__lte=now-timedelta(seconds=240))
        | Q(status=DatamailerOutboxStatus.PROCESSING, last_attempt_at__isnull=True),
    )
    ordered_event_ids = event_ids.order_by("created_at", "id")
    due_ids = ordered_event_ids.values_list("id", flat=True)[:limit]
    result = list(due_ids)
    return result


def _is_rate_limit_retry(event) -> bool:
    if event.status != DatamailerOutboxStatus.RETRYING:
        return False
    error = (event.last_error or "").lower()
    return "429" in error or "403" in error


def process_outbox_event_ids(
    event_ids,
    counts,
    *,
    max_duration_seconds: float | None = OUTBOX_RUN_MAX_SECONDS,
):
    started_monotonic = time.monotonic()
    for event_id in event_ids:
        if (
            max_duration_seconds is not None
            and counts["processed"] > 0
            and time.monotonic() - started_monotonic >= max_duration_seconds
        ):
            logger.info(
                "Stopping outbox run after %.1fs time budget (%s processed); "
                "remaining events will run on next tick.",
                time.monotonic() - started_monotonic,
                counts["processed"],
            )
            break
        event = DatamailerOutboxEvent.objects.get(id=event_id)
        dispatch_datamailer_outbox_event(event)
        event.refresh_from_db()
        count_processed_outbox_event(counts, event)
        if _is_rate_limit_retry(event):
            logger.warning(
                "Pausing outbox run after rate-limit/WAF response on event_id=%s.",
                event.event_id,
            )
            break


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
