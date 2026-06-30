import logging
from dataclasses import dataclass
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


@dataclass(frozen=True)
class DatamailerOutboxEventData:
    event_type: str
    idempotency_key: str
    ordering_key: str
    payload: dict[str, Any]
    dispatch_immediately: bool = True


def enqueue_datamailer_outbox_event(
    data: DatamailerOutboxEventData,
) -> DatamailerOutboxEvent:
    event_id = f"cmp-datamailer-event:{uuid4()}"
    event = DatamailerOutboxEvent.objects.create(
        idempotency_key=data.idempotency_key,
        event_id=event_id,
        event_type=data.event_type,
        ordering_key=data.ordering_key,
        payload=data.payload,
        occurred_at=timezone.now(),
        next_attempt_at=timezone.now(),
    )

    if data.dispatch_immediately and event.status in RETRYABLE_STATUSES:
        dispatch_datamailer_outbox_event(event)
        event.refresh_from_db()

    return event


def process_due_datamailer_outbox(*, limit=100, record_run=True) -> dict[str, int]:
    started_at = timezone.now()
    if record_run:
        run = _create_dispatch_run(started_at)
    else:
        run = None
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
    due_events = _due_outbox_events(now)
    dispatch_runs = _outbox_dispatch_runs()
    return {
        "event_counts": _outbox_event_counts(),
        "due_count": due_events.count(),
        "oldest_due": _oldest_due_outbox_event(due_events),
        "last_successful_run": dispatch_runs["last_successful_run"],
        "last_run": dispatch_runs["last_run"],
        "last_error_event": _last_error_outbox_event(),
    }


def _outbox_event_counts():
    event_counts = {}
    outbox_statuses = DatamailerOutboxStatus.values
    for status in outbox_statuses:
        count = DatamailerOutboxEvent.objects.filter(status=status).count()
        event_counts[status] = count
    return event_counts


def _due_outbox_events(now):
    return DatamailerOutboxEvent.objects.filter(
        status__in=RETRYABLE_STATUSES,
        next_attempt_at__lte=now,
    )


def _oldest_due_outbox_event(due_events):
    ordered_events = due_events.order_by("next_attempt_at", "created_at", "id")
    oldest_event = ordered_events.first()
    return oldest_event


def _outbox_dispatch_runs():
    last_successful_run = DatamailerOutboxDispatchRun.objects.filter(
        status=DatamailerOutboxDispatchRunStatus.SUCCESS,
    ).first()
    last_run = DatamailerOutboxDispatchRun.objects.first()
    return {
        "last_successful_run": last_successful_run,
        "last_run": last_run,
    }


def _last_error_outbox_event():
    return (
        DatamailerOutboxEvent.objects.exclude(last_error="")
        .order_by("-last_attempt_at", "-updated_at", "-id")
        .first()
    )


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
    config = _outbox_datamailer_config(event)
    if config is None:
        return

    if not _claim_outbox_event(event):
        return

    _dispatch_claimed_outbox_event(event, config)


def _outbox_datamailer_config(event):
    from course_management.datamailer.client import DatamailerConfig

    config = DatamailerConfig.from_settings()
    if config is None:
        _mark_failed(event, "Datamailer is not configured")
    return config


def _claim_outbox_event(event):
    with transaction.atomic():
        locked = DatamailerOutboxEvent.objects.select_for_update().get(id=event.id)
        if locked.status not in RETRYABLE_STATUSES:
            return False
        _mark_processing(locked)
        return True


def _mark_processing(event):
    event.status = DatamailerOutboxStatus.PROCESSING
    event.attempt_count += 1
    event.last_attempt_at = timezone.now()
    event.save(
        update_fields=[
            "status",
            "attempt_count",
            "last_attempt_at",
            "updated_at",
        ]
    )


def _dispatch_claimed_outbox_event(event, config):
    from course_management.datamailer.client import DatamailerClient

    client = DatamailerClient(config)
    try:
        response = _send_event(client, event.event_type, event.payload)
    except requests.RequestException as exc:
        if _handle_outbox_send_error(event, config, exc):
            raise
        return

    _mark_acked(event, response or {})


def _handle_outbox_send_error(event, config, exc):
    logger.exception(
        "Datamailer outbox dispatch failed for event_id=%s",
        event.event_id,
    )
    _mark_retry_or_failed(event, exc)
    return config.strict


def _upsert_contact_if_present(client, payload):
    contact_payload = payload.get("contact_payload")
    if contact_payload:
        client.upsert_contact(contact_payload)


def _send_member_upsert_event(client, payload):
    _upsert_contact_if_present(client, payload)
    return client.upsert_recipient_list_member(
        payload["list_key"],
        payload["source_object_key"],
        payload["member_payload"],
    )


def _send_member_remove_event(client, payload):
    return client.remove_recipient_list_member(
        payload["list_key"],
        payload["source_object_key"],
    )


def _send_members_bulk_upsert_event(client, payload):
    return client.bulk_upsert_recipient_list_members(
        payload["list_key"],
        payload["member_sync_payload"],
    )


def _send_contact_erase_event(client, payload):
    return client.erase_contact(payload["email"])


_OUTBOX_EVENT_SENDERS = {
    "recipient_list.member_upsert": _send_member_upsert_event,
    "recipient_list.member_remove": _send_member_remove_event,
    "recipient_list.members_bulk_upsert": _send_members_bulk_upsert_event,
    "contact.erase": _send_contact_erase_event,
}


def _send_event(client, event_type: str, payload: dict[str, Any]):
    sender = _OUTBOX_EVENT_SENDERS.get(event_type)
    if sender is None:
        raise ValueError(
            f"Unsupported Datamailer outbox event type: {event_type}"
        )
    return sender(client, payload)


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


def _http_error_status_code(exc):
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", 0)
    if status_code:
        return status_code
    return 0


def _is_non_retryable_http_error(exc):
    if not isinstance(exc, requests.HTTPError):
        return False

    status_code = _http_error_status_code(exc)
    if not status_code:
        return False
    is_server_error = status_code >= 500
    is_rate_limited = status_code == 429
    return not is_server_error and not is_rate_limited


def _status_for_error(exc, event):
    if event.attempt_count >= event.max_attempts:
        return DatamailerOutboxStatus.FAILED
    if _is_non_retryable_http_error(exc):
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
