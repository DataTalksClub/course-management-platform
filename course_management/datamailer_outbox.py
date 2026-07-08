from dataclasses import dataclass
from typing import Any
from uuid import uuid4

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
    dispatch_immediately: bool = True


def enqueue_datamailer_outbox_event(
    data: DatamailerOutboxEventData,
) -> DatamailerOutboxEvent:
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
            "dispatch_immediately": data.dispatch_immediately,
        },
    )

    if data.dispatch_immediately and event.status in RETRYABLE_STATUSES:
        from course_management.datamailer_outbox_dispatch import (
            dispatch_datamailer_outbox_event,
        )

        dispatch_datamailer_outbox_event(event)
        event.refresh_from_db()

    return event
