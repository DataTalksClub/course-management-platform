from typing import Any

from django.utils import timezone


def upsert_contact_if_present(client, payload):
    contact_payload = payload.get("contact_payload")
    if contact_payload:
        client.contacts.upsert_contact(contact_payload)


def send_recipient_list_member_upsert_event(client, payload):
    upsert_contact_if_present(client, payload)
    list_key = payload["list_key"]
    source_object_key = payload["source_object_key"]
    member_payload = payload["member_payload"]
    return client.recipient_lists.members.upsert(
        list_key,
        source_object_key,
        member_payload,
    )


def send_recipient_list_member_remove_event(client, payload):
    list_key = payload["list_key"]
    source_object_key = payload["source_object_key"]
    return client.recipient_lists.members.remove(
        list_key,
        source_object_key,
    )


def send_recipient_list_members_bulk_upsert_event(client, payload):
    list_key = payload["list_key"]
    member_sync_payload = payload["member_sync_payload"]
    return client.recipient_lists.members.bulk_upsert(
        list_key,
        member_sync_payload,
    )


def send_contact_erase_event(client, payload):
    email = payload["email"]
    return client.contacts.erase_contact(email)


def campaign_queue_recipient_count(response):
    response = response or {}
    recipient_count = response.get("recipient_count")
    if recipient_count is None:
        campaign_payload = response.get("campaign") or {}
        recipient_count = campaign_payload.get("recipient_count")
    return recipient_count


def send_campaign_queue_event(client, payload):
    from courses.models.course import EmailCampaign

    external_key = payload["external_key"]
    email_campaign_id = payload["email_campaign_id"]

    response = client.campaigns.queue_campaign(external_key)
    recipient_count = campaign_queue_recipient_count(response)

    EmailCampaign.objects.filter(id=email_campaign_id).update(
        status=EmailCampaign.Status.QUEUED,
        queued_at=timezone.now(),
        last_recipient_count=recipient_count,
        updated_at=timezone.now(),
    )
    return response


DATAMAILER_OUTBOX_EVENT_SENDERS = {
    "recipient_list.member_upsert": send_recipient_list_member_upsert_event,
    "recipient_list.member_remove": send_recipient_list_member_remove_event,
    "recipient_list.members_bulk_upsert": (
        send_recipient_list_members_bulk_upsert_event
    ),
    "contact.erase": send_contact_erase_event,
    "campaign.queue": send_campaign_queue_event,
}


def send_event(client, event_type: str, payload: dict[str, Any]):
    sender = DATAMAILER_OUTBOX_EVENT_SENDERS.get(event_type)
    if sender is None:
        raise ValueError(
            f"Unsupported Datamailer outbox event type: {event_type}"
        )
    return sender(client, payload)
