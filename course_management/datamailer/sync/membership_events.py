from dataclasses import dataclass
from typing import Any

from course_management.datamailer.keys import datamailer_ordering_key
from course_management.datamailer.payloads.base import (
    removed_recipient_list_member_payload,
)
from course_management.datamailer_outbox import (
    DatamailerOutboxEventData,
    enqueue_datamailer_outbox_event,
)


@dataclass(frozen=True)
class ContactMembershipSyncData:
    contact_payload: dict[str, Any] | None
    list_payload: object
    label: str
    obj: object


@dataclass(frozen=True)
class RecipientListMembershipRemoveData:
    list_payloads: list
    label: str
    obj: object


def sync_contact_and_membership(data):
    """Upsert a contact and its recipient-list membership in one event."""
    if data.contact_payload is None or data.list_payload is None:
        return

    ordering_key = datamailer_ordering_key(data.obj)
    event_data = DatamailerOutboxEventData(
        event_type="recipient_list.member_upsert",
        idempotency_key=(
            "recipient-list.member-upsert:"
            f"{data.list_payload.list_key}:"
            f"{data.list_payload.source_object_key}:"
            f"{data.obj.pk}:{data.obj.__class__.__name__}"
        ),
        ordering_key=ordering_key,
        payload={
            "contact_payload": data.contact_payload,
            "list_key": data.list_payload.list_key,
            "source_object_key": data.list_payload.source_object_key,
            "member_payload": data.list_payload.payload,
            "label": data.label,
            "object_id": data.obj.pk,
        },
    )
    enqueue_datamailer_outbox_event(event_data)


def remove_recipient_list_memberships(data) -> None:
    for list_payload in data.list_payloads:
        if list_payload is None:
            continue
        member_payload = removed_recipient_list_member_payload(
            list_payload.payload
        )
        ordering_key = datamailer_ordering_key(data.obj)
        event_data = DatamailerOutboxEventData(
            event_type="recipient_list.member_remove",
            idempotency_key=(
                "recipient-list.member-remove:"
                f"{list_payload.list_key}:"
                f"{list_payload.source_object_key}:"
                f"{data.obj.pk}:{data.obj.__class__.__name__}"
            ),
            ordering_key=ordering_key,
            payload={
                "list_key": list_payload.list_key,
                "source_object_key": list_payload.source_object_key,
                "member_payload": member_payload,
                "label": data.label,
                "object_id": data.obj.pk,
            },
        )
        enqueue_datamailer_outbox_event(event_data)
