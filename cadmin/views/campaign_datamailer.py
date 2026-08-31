import re
from dataclasses import dataclass

import requests
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone

from courses.models.course import EmailCampaign
from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)
from course_management.datamailer.payloads.email_campaigns import (
    email_campaign_datamailer_payload,
)


DATAMAILER_CAMPAIGN_UPSERT_ACTIONS = {
    "sync",
    "preview",
    "test_send",
    "queue",
}


@dataclass(frozen=True)
class DatamailerCampaignActionData:
    request: object
    email_campaign: object
    action: str
    client: DatamailerClient


def test_recipient_emails(value):
    emails = []
    raw_items = re.split(r"[\s,;]+", value or "")
    for raw_item in raw_items:
        email = raw_item.strip()
        if email:
            emails.append(email)
    return emails


def validate_test_recipient_count(emails):
    if not emails:
        raise ValidationError("Enter at least one test recipient.")
    if len(emails) > 25:
        raise ValidationError("Enter no more than 25 test recipients.")


def validate_test_recipient_emails(emails):
    for email in emails:
        validate_email(email)


def parse_test_recipients(value):
    emails = test_recipient_emails(value)
    validate_test_recipient_count(emails)
    validate_test_recipient_emails(emails)
    return emails


def datamailer_campaign_context(email_campaign):
    payload = email_campaign_datamailer_payload(email_campaign)
    return {
        "datamailer_external_key": email_campaign.external_key,
        "datamailer_payload": payload,
    }


def datamailer_campaign_client_or_message(request):
    config = DatamailerConfig.from_settings()
    if config is None:
        messages.error(
            request,
            "Datamailer is not configured for campaign operations.",
        )
        return None
    return DatamailerClient(config)


def datamailer_campaign_queue_recipient_count(response):
    response = response or {}
    recipient_count = response.get("recipient_count")
    if recipient_count is None:
        campaign_payload = response.get("campaign") or {}
        recipient_count = campaign_payload.get("recipient_count", 0)
    return recipient_count


def sync_datamailer_campaign_action(request, client, email_campaign):
    if email_campaign.status == EmailCampaign.Status.DRAFT:
        email_campaign.status = EmailCampaign.Status.SYNCED
        email_campaign.save(update_fields=["status", "updated_at"])
    messages.success(request, "Datamailer campaign draft synced.")
    return None, True


def preview_datamailer_campaign_action(request, client, email_campaign):
    preview = client.campaigns.preview_campaign(email_campaign.external_key)
    messages.success(request, "Datamailer campaign preview rendered.")
    return preview, False


def test_send_datamailer_campaign_action(request, client, email_campaign):
    raw_recipients = request.POST.get("test_recipients", "")
    recipients = parse_test_recipients(raw_recipients)
    recipient_count = len(recipients)
    client.campaigns.test_send_campaign(
        email_campaign.external_key, recipients
    )
    messages.success(
        request,
        f"Datamailer test send queued for {recipient_count} recipient(s).",
    )
    return None, True


def queue_datamailer_campaign_action(request, client, email_campaign):
    response = client.campaigns.queue_campaign(email_campaign.external_key)
    recipient_count = datamailer_campaign_queue_recipient_count(response)
    email_campaign.status = EmailCampaign.Status.QUEUED
    email_campaign.queued_at = timezone.now()
    email_campaign.last_recipient_count = recipient_count
    email_campaign.save(
        update_fields=[
            "status",
            "queued_at",
            "last_recipient_count",
            "updated_at",
        ]
    )
    messages.success(
        request,
        f"Datamailer campaign queued for {recipient_count} recipient(s).",
    )
    return None, True


def cancel_datamailer_campaign_action(request, client, email_campaign):
    client.campaigns.cancel_campaign(email_campaign.external_key)
    email_campaign.status = EmailCampaign.Status.CANCELLED
    email_campaign.cancelled_at = timezone.now()
    email_campaign.save(
        update_fields=["status", "cancelled_at", "updated_at"]
    )
    messages.success(request, "Datamailer campaign cancelled.")
    return None, True


DATAMAILER_CAMPAIGN_ACTION_HANDLERS = {
    "sync": sync_datamailer_campaign_action,
    "preview": preview_datamailer_campaign_action,
    "test_send": test_send_datamailer_campaign_action,
    "queue": queue_datamailer_campaign_action,
    "cancel": cancel_datamailer_campaign_action,
}


def run_datamailer_campaign_action(data):
    handler = DATAMAILER_CAMPAIGN_ACTION_HANDLERS.get(data.action)
    if handler:
        return handler(data.request, data.client, data.email_campaign)

    messages.error(data.request, "Unknown Datamailer campaign action.")
    return None, False


def upsert_datamailer_campaign_if_needed(data):
    if data.action not in DATAMAILER_CAMPAIGN_UPSERT_ACTIONS:
        return

    payload = email_campaign_datamailer_payload(data.email_campaign)
    data.client.campaigns.upsert_campaign(
        data.email_campaign.external_key, payload
    )


def perform_datamailer_campaign_action(data):
    upsert_datamailer_campaign_if_needed(data)
    return run_datamailer_campaign_action(data)


def datamailer_campaign_action_data(request, email_campaign, client):
    raw_action = request.POST.get("datamailer_action", "")
    action = raw_action.strip()
    return DatamailerCampaignActionData(
        request=request,
        email_campaign=email_campaign,
        action=action,
        client=client,
    )


def handle_datamailer_campaign_action(request, email_campaign):
    client = datamailer_campaign_client_or_message(request)
    if client is None:
        return None, True

    action_data = datamailer_campaign_action_data(
        request,
        email_campaign,
        client,
    )

    try:
        return perform_datamailer_campaign_action(action_data)
    except ValidationError as exc:
        message = "; ".join(exc.messages)
        messages.error(request, message)
        return None, False
    except requests.RequestException as exc:
        messages.error(
            request,
            f"Datamailer campaign request failed: {exc}",
        )
        return None, False
