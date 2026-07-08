import logging

import requests
from django.db import transaction
from django.utils import timezone

from course_management.observability import record_event
from course_management.datamailer_outbox import RETRYABLE_STATUSES
from course_management.datamailer_outbox_senders import send_event
from course_management.datamailer_outbox_retry import (
    retry_delay,
    status_for_error,
)
from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
)


logger = logging.getLogger(__name__)


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
        locked = DatamailerOutboxEvent.objects.select_for_update().get(
            id=event.id
        )
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
    record_event(
        "datamailer.outbox_acked",
        properties={
            "event_id": event.event_id,
            "event_type": event.event_type,
            "outbox_event_id": event.id,
        },
    )


def mark_retry_or_failed(event, exc):
    event.refresh_from_db()
    status = status_for_error(exc, event)
    now = timezone.now()
    last_error = str(exc)
    updates = {
        "status": status,
        "last_error": last_error,
        "updated_at": now,
    }
    if status == DatamailerOutboxStatus.RETRYING:
        retry_delta = retry_delay(event.attempt_count)
        updates["next_attempt_at"] = now + retry_delta
    DatamailerOutboxEvent.objects.filter(id=event.id).update(**updates)
    record_event(
        "datamailer.outbox_dispatch_failed",
        properties={
            "event_id": event.event_id,
            "event_type": event.event_type,
            "outbox_event_id": event.id,
            "status": status,
            "attempt_count": event.attempt_count,
        },
    )


def mark_failed(event, message):
    now = timezone.now()
    DatamailerOutboxEvent.objects.filter(id=event.id).update(
        status=DatamailerOutboxStatus.FAILED,
        last_error=message,
        updated_at=now,
    )
    record_event(
        "datamailer.outbox_failed",
        properties={
            "event_id": event.event_id,
            "event_type": event.event_type,
            "outbox_event_id": event.id,
            "status": DatamailerOutboxStatus.FAILED,
            "reason": message,
        },
    )


def json_response_payload(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"items": value}
    if value in (None, "", True, False):
        return {}
    response_value = str(value)
    return {"value": response_value}
