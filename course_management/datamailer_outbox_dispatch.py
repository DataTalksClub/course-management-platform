import logging

import requests
from django.db import transaction
from django.utils import timezone

from course_management.datamailer_outbox import RETRYABLE_STATUSES
from course_management.datamailer_outbox_senders import send_event
from course_management.datamailer_outbox_retry import (
    retry_delay,
    status_for_error,
)
from data.models import (
    DatamailerOutboxDispatchRun,
    DatamailerOutboxDispatchRunStatus,
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
)


logger = logging.getLogger(__name__)


def process_due_datamailer_outbox(*, limit=100, record_run=True) -> dict[str, int]:
    started_at = timezone.now()
    if record_run:
        run = create_dispatch_run(started_at)
    else:
        run = None
    event_ids = due_outbox_event_ids(limit)
    counts = initial_outbox_counts()

    try:
        process_outbox_event_ids(event_ids, counts)
    except Exception as exc:
        finish_dispatch_run_if_present(
            run,
            counts,
            status=DatamailerOutboxDispatchRunStatus.FAILED,
            last_error=str(exc),
        )
        raise

    finish_dispatch_run_if_present(
        run,
        counts,
        status=DatamailerOutboxDispatchRunStatus.SUCCESS,
        last_error="",
    )
    return counts


def create_dispatch_run(started_at):
    return DatamailerOutboxDispatchRun.objects.create(
        started_at=started_at,
        status=DatamailerOutboxDispatchRunStatus.SUCCESS,
    )


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


def initial_outbox_counts():
    return {"processed": 0, "acked": 0, "retrying": 0, "failed": 0}


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


def dispatch_datamailer_outbox_event(event: DatamailerOutboxEvent) -> None:
    config = outbox_datamailer_config(event)
    if config is None:
        return

    if not claim_outbox_event(event):
        return

    dispatch_claimed_outbox_event(event, config)


def outbox_datamailer_config(event):
    from course_management.datamailer.client import DatamailerConfig

    config = DatamailerConfig.from_settings()
    if config is None:
        mark_failed(event, "Datamailer is not configured")
    return config


def claim_outbox_event(event):
    with transaction.atomic():
        locked = DatamailerOutboxEvent.objects.select_for_update().get(id=event.id)
        if locked.status not in RETRYABLE_STATUSES:
            return False
        mark_processing(locked)
        return True


def mark_processing(event):
    now = timezone.now()
    event.status = DatamailerOutboxStatus.PROCESSING
    event.attempt_count += 1
    event.last_attempt_at = now
    event.save(
        update_fields=[
            "status",
            "attempt_count",
            "last_attempt_at",
            "updated_at",
        ]
    )


def dispatch_claimed_outbox_event(event, config):
    from course_management.datamailer.client import DatamailerClient

    client = DatamailerClient(config)
    try:
        response = send_event(client, event.event_type, event.payload)
    except requests.RequestException as exc:
        if handle_outbox_send_error(event, config, exc):
            raise
        return

    mark_acked(event, response or {})


def handle_outbox_send_error(event, config, exc):
    logger.exception(
        "Datamailer outbox dispatch failed for event_id=%s",
        event.event_id,
    )
    mark_retry_or_failed(event, exc)
    return config.strict


def mark_acked(event, response_payload):
    now = timezone.now()
    response_data = json_response_payload(response_payload)
    DatamailerOutboxEvent.objects.filter(id=event.id).update(
        status=DatamailerOutboxStatus.ACKED,
        acked_at=now,
        next_attempt_at=now,
        last_error="",
        response_payload=response_data,
        updated_at=now,
    )


def mark_retry_or_failed(event, exc):
    event.refresh_from_db()
    status = status_for_error(exc, event)
    now = timezone.now()
    updates = {
        "status": status,
        "last_error": str(exc),
        "updated_at": now,
    }
    if status == DatamailerOutboxStatus.RETRYING:
        retry_delta = retry_delay(event.attempt_count)
        updates["next_attempt_at"] = now + retry_delta
    DatamailerOutboxEvent.objects.filter(id=event.id).update(**updates)


def mark_failed(event, message):
    now = timezone.now()
    DatamailerOutboxEvent.objects.filter(id=event.id).update(
        status=DatamailerOutboxStatus.FAILED,
        last_error=message,
        updated_at=now,
    )


def json_response_payload(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"items": value}
    if value in (None, "", True, False):
        return {}
    return {"value": str(value)}
