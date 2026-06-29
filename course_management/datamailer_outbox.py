import logging
from datetime import timedelta
from typing import Any
from uuid import uuid4

import requests
from django.db import transaction
from django.utils import timezone

from data.models import (
    DatamailerOutboxDispatchRun,
    DatamailerOutboxDispatchRunStatus,
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
)

logger = logging.getLogger(__name__)

RETRYABLE_STATUSES = {
    DatamailerOutboxStatus.PENDING,
    DatamailerOutboxStatus.RETRYING,
}


def enqueue_datamailer_outbox_event(
    *,
    event_type: str,
    idempotency_key: str,
    ordering_key: str,
    payload: dict[str, Any],
    dispatch_immediately: bool = True,
) -> DatamailerOutboxEvent:
    event_id = f"cmp-datamailer-event:{uuid4()}"
    event = DatamailerOutboxEvent.objects.create(
        idempotency_key=idempotency_key,
        event_id=event_id,
        event_type=event_type,
        ordering_key=ordering_key,
        payload=payload,
        occurred_at=timezone.now(),
        next_attempt_at=timezone.now(),
    )

    if dispatch_immediately and event.status in RETRYABLE_STATUSES:
        dispatch_datamailer_outbox_event(event)
        event.refresh_from_db()

    return event


def process_due_datamailer_outbox(*, limit=100, record_run=True) -> dict[str, int]:
    started_at = timezone.now()
    run = _create_dispatch_run(started_at) if record_run else None
    event_ids = _due_outbox_event_ids(limit)
    counts = _initial_outbox_counts()

    try:
        _process_outbox_event_ids(event_ids, counts)
    except Exception as exc:
        _finish_dispatch_run_if_present(
            run,
            counts,
            status=DatamailerOutboxDispatchRunStatus.FAILED,
            last_error=str(exc),
        )
        raise

    _finish_dispatch_run_if_present(
        run,
        counts,
        status=DatamailerOutboxDispatchRunStatus.SUCCESS,
        last_error="",
    )
    return counts


def _create_dispatch_run(started_at):
    return DatamailerOutboxDispatchRun.objects.create(
        started_at=started_at,
        status=DatamailerOutboxDispatchRunStatus.SUCCESS,
    )


def _due_outbox_event_ids(limit):
    now = timezone.now()
    return list(
        DatamailerOutboxEvent.objects.filter(
            status__in=RETRYABLE_STATUSES,
            next_attempt_at__lte=now,
        )
        .order_by("created_at", "id")
        .values_list("id", flat=True)[:limit]
    )


def _initial_outbox_counts():
    return {"processed": 0, "acked": 0, "retrying": 0, "failed": 0}


def _process_outbox_event_ids(event_ids, counts):
    for event_id in event_ids:
        event = DatamailerOutboxEvent.objects.get(id=event_id)
        dispatch_datamailer_outbox_event(event)
        event.refresh_from_db()
        _count_processed_outbox_event(counts, event)


def _count_processed_outbox_event(counts, event):
    counts["processed"] += 1
    if event.status in {
        DatamailerOutboxStatus.ACKED,
        DatamailerOutboxStatus.RETRYING,
        DatamailerOutboxStatus.FAILED,
    }:
        counts[event.status] += 1


def _finish_dispatch_run_if_present(run, counts, *, status, last_error):
    if run is None:
        return

    _finish_dispatch_run(
        run,
        counts,
        status=status,
        last_error=last_error,
    )


def datamailer_outbox_status_summary() -> dict[str, Any]:
    now = timezone.now()
    event_counts = {
        status: DatamailerOutboxEvent.objects.filter(status=status).count()
        for status in DatamailerOutboxStatus.values
    }
    due_count = DatamailerOutboxEvent.objects.filter(
        status__in=RETRYABLE_STATUSES,
        next_attempt_at__lte=now,
    ).count()
    oldest_due = (
        DatamailerOutboxEvent.objects.filter(
            status__in=RETRYABLE_STATUSES,
            next_attempt_at__lte=now,
        )
        .order_by("next_attempt_at", "created_at", "id")
        .first()
    )
    last_successful_run = DatamailerOutboxDispatchRun.objects.filter(
        status=DatamailerOutboxDispatchRunStatus.SUCCESS,
    ).first()
    last_run = DatamailerOutboxDispatchRun.objects.first()
    last_error_event = (
        DatamailerOutboxEvent.objects.exclude(last_error="")
        .order_by("-last_attempt_at", "-updated_at", "-id")
        .first()
    )
    return {
        "event_counts": event_counts,
        "due_count": due_count,
        "oldest_due": oldest_due,
        "last_successful_run": last_successful_run,
        "last_run": last_run,
        "last_error_event": last_error_event,
    }


def _finish_dispatch_run(run, counts, *, status, last_error):
    run.status = status
    run.finished_at = timezone.now()
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
    from course_management.datamailer import DatamailerClient, DatamailerConfig

    config = DatamailerConfig.from_settings()
    if config is None:
        _mark_failed(event, "Datamailer is not configured")
        return

    with transaction.atomic():
        locked = DatamailerOutboxEvent.objects.select_for_update().get(id=event.id)
        if locked.status not in RETRYABLE_STATUSES:
            return
        locked.status = DatamailerOutboxStatus.PROCESSING
        locked.attempt_count += 1
        locked.last_attempt_at = timezone.now()
        locked.save(
            update_fields=[
                "status",
                "attempt_count",
                "last_attempt_at",
                "updated_at",
            ]
        )

    client = DatamailerClient(config)
    try:
        response = _send_event(client, event.event_type, event.payload)
    except requests.RequestException as exc:
        logger.exception(
            "Datamailer outbox dispatch failed for event_id=%s",
            event.event_id,
        )
        _mark_retry_or_failed(event, exc)
        if config.strict:
            raise
        return

    _mark_acked(event, response or {})


def _send_event(client, event_type: str, payload: dict[str, Any]):
    if event_type == "recipient_list.member_upsert":
        contact_payload = payload.get("contact_payload")
        if contact_payload:
            client.upsert_contact(contact_payload)
        return client.upsert_recipient_list_member(
            payload["list_key"],
            payload["source_object_key"],
            payload["member_payload"],
        )

    if event_type == "recipient_list.member_remove":
        return client.remove_recipient_list_member(
            payload["list_key"],
            payload["source_object_key"],
        )

    if event_type == "recipient_list.members_bulk_upsert":
        return client.bulk_upsert_recipient_list_members(
            payload["list_key"],
            payload["member_sync_payload"],
        )

    if event_type == "contact.erase":
        return client.erase_contact(payload["email"])

    raise ValueError(f"Unsupported Datamailer outbox event type: {event_type}")


def _mark_acked(event, response_payload):
    DatamailerOutboxEvent.objects.filter(id=event.id).update(
        status=DatamailerOutboxStatus.ACKED,
        acked_at=timezone.now(),
        next_attempt_at=timezone.now(),
        last_error="",
        response_payload=_json_response_payload(response_payload),
        updated_at=timezone.now(),
    )


def _mark_retry_or_failed(event, exc):
    event.refresh_from_db()
    status = _status_for_error(exc, event)
    updates = {
        "status": status,
        "last_error": str(exc),
        "updated_at": timezone.now(),
    }
    if status == DatamailerOutboxStatus.RETRYING:
        updates["next_attempt_at"] = timezone.now() + _retry_delay(event.attempt_count)
    DatamailerOutboxEvent.objects.filter(id=event.id).update(**updates)


def _mark_failed(event, message):
    DatamailerOutboxEvent.objects.filter(id=event.id).update(
        status=DatamailerOutboxStatus.FAILED,
        last_error=message,
        updated_at=timezone.now(),
    )


def _status_for_error(exc, event):
    if event.attempt_count >= event.max_attempts:
        return DatamailerOutboxStatus.FAILED
    if isinstance(exc, requests.HTTPError):
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", 0) or 0
        if status_code and status_code < 500 and status_code != 429:
            return DatamailerOutboxStatus.FAILED
    return DatamailerOutboxStatus.RETRYING


def _retry_delay(attempt_count):
    delay_seconds = min(300, 2 ** max(attempt_count - 1, 0))
    return timedelta(seconds=delay_seconds)


def _json_response_payload(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"items": value}
    if value in (None, "", True, False):
        return {}
    return {"value": str(value)}
