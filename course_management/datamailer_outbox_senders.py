from typing import Any


def upsert_contact_if_present(client, payload):
    contact_payload = payload.get("contact_payload")
    if contact_payload:
        client.upsert_contact(contact_payload)


def send_member_upsert_event(client, payload):
    upsert_contact_if_present(client, payload)
    return client.upsert_recipient_list_member(
        payload["list_key"],
        payload["source_object_key"],
        payload["member_payload"],
    )


def send_member_remove_event(client, payload):
    return client.remove_recipient_list_member(
        payload["list_key"],
        payload["source_object_key"],
    )


def send_members_bulk_upsert_event(client, payload):
    return client.bulk_upsert_recipient_list_members(
        payload["list_key"],
        payload["member_sync_payload"],
    )


def send_contact_erase_event(client, payload):
    return client.erase_contact(payload["email"])


OUTBOX_EVENT_SENDERS = {
    "recipient_list.member_upsert": send_member_upsert_event,
    "recipient_list.member_remove": send_member_remove_event,
    "recipient_list.members_bulk_upsert": send_members_bulk_upsert_event,
    "contact.erase": send_contact_erase_event,
}


def send_event(client, event_type: str, payload: dict[str, Any]):
    sender = OUTBOX_EVENT_SENDERS.get(event_type)
    if sender is None:
        raise ValueError(
            f"Unsupported Datamailer outbox event type: {event_type}"
        )
    return sender(client, payload)
