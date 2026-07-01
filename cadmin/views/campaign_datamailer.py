import re

import requests
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)
from course_management.datamailer.keys import (
    registration_campaign_external_key,
)
from course_management.datamailer.payloads import (
    registration_campaign_datamailer_payload,
)


DATAMAILER_CAMPAIGN_UPSERT_ACTIONS = {
    "sync",
    "preview",
    "test_send",
    "queue",
}


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


def datamailer_campaign_context(campaign):
    return {
        "datamailer_external_key": registration_campaign_external_key(
            campaign
        ),
        "datamailer_payload": registration_campaign_datamailer_payload(
            campaign
        ),
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


def sync_datamailer_campaign_action(request, client, external_key):
    messages.success(request, "Datamailer campaign draft synced.")
    return None, True


def preview_datamailer_campaign_action(request, client, external_key):
    preview = client.preview_campaign(external_key)
    messages.success(request, "Datamailer campaign preview rendered.")
    return preview, False


def test_send_datamailer_campaign_action(request, client, external_key):
    raw_recipients = request.POST.get("test_recipients", "")
    recipients = parse_test_recipients(raw_recipients)
    recipient_count = len(recipients)
    client.test_send_campaign(external_key, recipients)
    messages.success(
        request,
        f"Datamailer test send queued for {recipient_count} recipient(s).",
    )
    return None, True


def queue_datamailer_campaign_action(request, client, external_key):
    response = client.queue_campaign(external_key)
    recipient_count = datamailer_campaign_queue_recipient_count(response)
    messages.success(
        request,
        f"Datamailer campaign queued for {recipient_count} recipient(s).",
    )
    return None, True


def cancel_datamailer_campaign_action(request, client, external_key):
    client.cancel_campaign(external_key)
    messages.success(request, "Datamailer campaign cancelled.")
    return None, True


DATAMAILER_CAMPAIGN_ACTION_HANDLERS = {
    "sync": sync_datamailer_campaign_action,
    "preview": preview_datamailer_campaign_action,
    "test_send": test_send_datamailer_campaign_action,
    "queue": queue_datamailer_campaign_action,
    "cancel": cancel_datamailer_campaign_action,
}


def run_datamailer_campaign_action(
    request,
    action,
    client,
    external_key,
):
    handler = DATAMAILER_CAMPAIGN_ACTION_HANDLERS.get(action)
    if handler:
        return handler(request, client, external_key)

    messages.error(request, "Unknown Datamailer campaign action.")
    return None, False


def upsert_datamailer_campaign_if_needed(action, client, external_key, campaign):
    if action not in DATAMAILER_CAMPAIGN_UPSERT_ACTIONS:
        return

    payload = registration_campaign_datamailer_payload(campaign)
    client.upsert_campaign(external_key, payload)


def handle_datamailer_campaign_action(request, campaign):
    raw_action = request.POST.get("datamailer_action", "")
    action = raw_action.strip()
    client = datamailer_campaign_client_or_message(request)
    if client is None:
        return None, True

    external_key = registration_campaign_external_key(campaign)

    try:
        upsert_datamailer_campaign_if_needed(
            action,
            client,
            external_key,
            campaign,
        )
        return run_datamailer_campaign_action(
            request,
            action,
            client,
            external_key,
        )
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
