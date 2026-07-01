from typing import Any


def upsert_contact_if_present(client, payload):
    contact_payload = payload.get("contact_payload")
    if contact_payload:
        client.upsert_contact(contact_payload)


def send_recipient_list_member_upsert_event(client, payload):
    upsert_contact_if_present(client, payload)
    list_key = payload["list_key"]
    source_object_key = payload["source_object_key"]
    member_payload = payload["member_payload"]
    return client.upsert_recipient_list_member(
        list_key,
        source_object_key,
        member_payload,
    )


def send_recipient_list_member_remove_event(client, payload):
    list_key = payload["list_key"]
    source_object_key = payload["source_object_key"]
    return client.remove_recipient_list_member(list_key, source_object_key)


def send_recipient_list_members_bulk_upsert_event(client, payload):
    list_key = payload["list_key"]
    member_sync_payload = payload["member_sync_payload"]
    return client.bulk_upsert_recipient_list_members(
        list_key,
        member_sync_payload,
    )


def send_contact_erase_event(client, payload):
    email = payload["email"]
    return client.erase_contact(email)


DATAMAILER_OUTBOX_EVENT_SENDERS = {
    "recipient_list.member_upsert": send_recipient_list_member_upsert_event,
    "recipient_list.member_remove": send_recipient_list_member_remove_event,
    "recipient_list.members_bulk_upsert": (
        send_recipient_list_members_bulk_upsert_event
    ),
    "contact.erase": send_contact_erase_event,
}


def send_event(client, event_type: str, payload: dict[str, Any]):
    sender = DATAMAILER_OUTBOX_EVENT_SENDERS.get(event_type)
    if sender is None:
        raise ValueError(
            f"Unsupported Datamailer outbox event type: {event_type}"
        )
    return sender(client, payload)
