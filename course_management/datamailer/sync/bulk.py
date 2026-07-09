from dataclasses import dataclass
from typing import Any

from course_management.datamailer.client import DatamailerConfig
from course_management.datamailer.payloads.send import (
    recipient_list_member_sync_payload,
)
from course_management.datamailer_outbox import (
    DatamailerOutboxEventData,
    enqueue_datamailer_outbox_event,
)
from data.models import DatamailerOutboxStatus


@dataclass(frozen=True)
class RecipientListBulkUpsertData:
    config: DatamailerConfig
    list_key: str
    payload: dict[str, Any]
    idempotency_key: str
    ordering_key: str


def enqueue_recipient_list_bulk_upsert(data):
    member_sync_payload = recipient_list_member_sync_payload(
        data.config,
        data.payload,
    )
    event_data = DatamailerOutboxEventData(
        event_type="recipient_list.members_bulk_upsert",
        idempotency_key=(
            "recipient-list.members-bulk-upsert:"
            f"{data.idempotency_key}"
        ),
        ordering_key=data.ordering_key,
        payload={
            "list_key": data.list_key,
            "member_sync_payload": member_sync_payload,
        },
        # Bulk upsert is called before a recipient-list send (campaigns,
        # certificates), which needs the ACKED status synchronously to decide
        # whether to proceed. All other outbox events are deferred to the
        # scheduled processor so request-time submissions are not blocked.
        dispatch_immediately=True,
    )
    return enqueue_datamailer_outbox_event(event_data)


def bulk_upsert_recipient_list_members_before_send(data) -> bool:
    event = enqueue_recipient_list_bulk_upsert(data)
    return event.status == DatamailerOutboxStatus.ACKED
