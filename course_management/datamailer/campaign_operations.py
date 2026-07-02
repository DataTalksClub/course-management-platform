from dataclasses import dataclass
from pathlib import Path

from django.core.management.base import CommandError


@dataclass(frozen=True)
class DatamailerCampaignRunData:
    client: object
    external_key: str
    options: dict


def read_body(*, inline="", file_path=""):
    if inline and file_path:
        raise CommandError(
            "Provide either inline body text or a body file, not both."
        )
    if file_path:
        path = Path(file_path)
        body_text = path.read_text(encoding="utf-8")
        return body_text
    return inline


def parse_metadata(items):
    metadata = {}
    for item in items:
        if "=" not in item:
            raise CommandError("--metadata values must be key=value pairs.")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise CommandError("--metadata keys cannot be empty.")
        metadata[key] = value
    return metadata


def campaign_bodies(options):
    html_body = read_body(
        inline=options["html"],
        file_path=options["html_file"],
    )
    text_body = read_body(
        inline=options["text"],
        file_path=options["text_file"],
    )
    if not html_body.strip() and not text_body.strip():
        raise CommandError(
            "Provide --html, --html-file, --text, or --text-file."
        )
    return html_body, text_body


def required_campaign_option(options, key, error_message):
    value = options[key].strip()
    if not value:
        raise CommandError(error_message)
    return value


def campaign_optional_fields(options):
    optional_fields = {}
    if options["recipient_list_key"]:
        optional_fields["recipient_list_key"] = options["recipient_list_key"]
    if options["scheduled_at"]:
        optional_fields["scheduled_at"] = options["scheduled_at"]
    return optional_fields


def campaign_payload(options):
    html_body, text_body = campaign_bodies(options)
    subject = required_campaign_option(
        options,
        "subject",
        "--subject is required.",
    )
    category_tag = required_campaign_option(
        options,
        "category_tag",
        "--category-tag is required.",
    )
    metadata = parse_metadata(options["metadata"])

    payload = {
        "subject": subject,
        "preview_text": options["preview_text"],
        "html_body": html_body,
        "text_body": text_body,
        "category_tag": category_tag,
        "include_tags": options["include_tag"],
        "exclude_tags": options["exclude_tag"],
        "metadata": metadata,
    }
    optional_fields = campaign_optional_fields(options)
    payload.update(optional_fields)
    return payload


def run_campaign_requests(data):
    payload = campaign_payload(data.options)
    upsert_response = data.client.campaigns.upsert_campaign(
        data.external_key,
        payload,
    )
    responses = {
        "upsert": upsert_response
    }
    action_responses = run_campaign_actions(data)
    responses.update(action_responses)
    return responses


def run_campaign_actions(data):
    responses = {}
    options = data.options
    if options["preview"]:
        responses["preview"] = data.client.campaigns.preview_campaign(data.external_key)
    if options["test_send"]:
        responses["test_send"] = data.client.campaigns.test_send_campaign(
            data.external_key,
            options["test_send"],
        )
    if options["queue"]:
        responses["queue"] = data.client.campaigns.queue_campaign(data.external_key)
    if options["cancel"]:
        responses["cancel"] = data.client.campaigns.cancel_campaign(data.external_key)
    return responses
