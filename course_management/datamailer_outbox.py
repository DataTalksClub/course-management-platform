import logging
from datetime import timedelta
from typing import Any
from uuid import uuid4

import requests
from django.db import transaction
from django.utils import timezone

from data.models import DatamailerOutboxEvent, DatamailerOutboxStatus

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


def process_due_datamailer_outbox(*, limit=100) -> dict[str, int]:
    now = timezone.now()
    event_ids = list(
        DatamailerOutboxEvent.objects.filter(
            status__in=RETRYABLE_STATUSES,
            next_attempt_at__lte=now,
        )
        .order_by("created_at", "id")
        .values_list("id", flat=True)[:limit]
    )
    counts = {"processed": 0, "acked": 0, "retrying": 0, "failed": 0}
    for event_id in event_ids:
        event = DatamailerOutboxEvent.objects.get(id=event_id)
        dispatch_datamailer_outbox_event(event)
        event.refresh_from_db()
        counts["processed"] += 1
        if event.status in {
            DatamailerOutboxStatus.ACKED,
            DatamailerOutboxStatus.RETRYING,
            DatamailerOutboxStatus.FAILED,
        }:
            counts[event.status] += 1
    return counts


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
        return client.upsert_recipient_list_member(
            payload["list_key"],
            payload["source_object_key"],
            payload["member_payload"],
        )

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
