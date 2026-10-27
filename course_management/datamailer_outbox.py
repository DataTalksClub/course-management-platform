from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from course_management.observability import record_event
from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
)

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
    dispatch_immediately: bool | None = None


def enqueue_datamailer_outbox_events(items):
    """Batch existing outbox writes; preserve immediate-dispatch semantics."""
    items = list(items)
    if any(
        item.dispatch_immediately
        if item.dispatch_immediately is not None
        else getattr(settings, "RELAY_OUTBOX_DISPATCH_IMMEDIATELY", False)
        for item in items
    ):
        return [enqueue_datamailer_outbox_event(item) for item in items]

    now = timezone.now()
    events = [
        DatamailerOutboxEvent(
            idempotency_key=item.idempotency_key,
            event_id=f"cmp-datamailer-event:{uuid4()}",
            event_type=item.event_type,
            ordering_key=item.ordering_key,
            payload=item.payload,
            occurred_at=now,
            next_attempt_at=now,
        ) for item in items
    ]
    with transaction.atomic():
        DatamailerOutboxEvent.objects.bulk_create(events, batch_size=250)
    for event in events:
        record_event(
            "datamailer.outbox_enqueued",
            properties={
                "event_id": event.event_id,
                "event_type": event.event_type,
                "outbox_event_id": event.id,
                "status": event.status,
                "dispatch_immediately": False,
            },
        )
    return events


def enqueue_datamailer_outbox_event(
    data: DatamailerOutboxEventData,
) -> DatamailerOutboxEvent:
    should_dispatch = (
        data.dispatch_immediately
        if data.dispatch_immediately is not None
        else getattr(settings, "RELAY_OUTBOX_DISPATCH_IMMEDIATELY", False)
    )
    event_uuid = uuid4()
    event_id = f"cmp-datamailer-event:{event_uuid}"
    now = timezone.now()
    event = DatamailerOutboxEvent.objects.create(
        idempotency_key=data.idempotency_key,
        event_id=event_id,
        event_type=data.event_type,
        ordering_key=data.ordering_key,
        payload=data.payload,
        occurred_at=now,
        next_attempt_at=now,
    )
    record_event(
        "datamailer.outbox_enqueued",
        properties={
            "event_id": event.event_id,
            "event_type": event.event_type,
            "outbox_event_id": event.id,
            "status": event.status,
            "dispatch_immediately": should_dispatch,
        },
    )

    if should_dispatch and event.status in RETRYABLE_STATUSES:
        from course_management.datamailer_outbox_dispatch import (
            dispatch_datamailer_outbox_event,
        )

        dispatch_datamailer_outbox_event(event)
        event.refresh_from_db()

    return event
