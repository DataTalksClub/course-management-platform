from typing import Any


def upsert_contact_if_present(client, payload):
    contact_payload = payload.get("contact_payload")
    if contact_payload:
        client.upsert_contact(contact_payload)


def send_event(client, event_type: str, payload: dict[str, Any]):
    if event_type == "recipient_list.member_upsert":
        upsert_contact_if_present(client, payload)
        list_key = payload["list_key"]
        source_object_key = payload["source_object_key"]
        member_payload = payload["member_payload"]
        return client.upsert_recipient_list_member(
            list_key,
            source_object_key,
            member_payload,
        )

    if event_type == "recipient_list.member_remove":
        list_key = payload["list_key"]
        source_object_key = payload["source_object_key"]
        return client.remove_recipient_list_member(list_key, source_object_key)

    if event_type == "recipient_list.members_bulk_upsert":
        list_key = payload["list_key"]
        member_sync_payload = payload["member_sync_payload"]
        return client.bulk_upsert_recipient_list_members(
            list_key,
            member_sync_payload,
        )

    if event_type == "contact.erase":
        email = payload["email"]
        return client.erase_contact(email)

    raise ValueError(f"Unsupported Datamailer outbox event type: {event_type}")
