import json
from pathlib import Path

import requests
from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)


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


class Command(BaseCommand):
    help = "Create/update and optionally operate a Datamailer campaign."

    def add_arguments(self, parser):
        parser.add_argument("external_key", help="Stable external campaign key.")
        self.add_content_arguments(parser)
        self.add_tag_filter_arguments(parser)
        self.add_campaign_metadata_arguments(parser)
        self.add_action_arguments(parser)
        self.add_output_arguments(parser)

    def add_content_arguments(self, parser):
        parser.add_argument("--subject", default="", help="Campaign subject.")
        parser.add_argument(
            "--preview-text",
            default="",
            help="Inbox preview text.",
        )
        parser.add_argument("--html", default="", help="Inline HTML body.")
        parser.add_argument(
            "--html-file",
            default="",
            help="Path to an HTML body file.",
        )
        parser.add_argument("--text", default="", help="Inline text body.")
        parser.add_argument(
            "--text-file",
            default="",
            help="Path to a text body file.",
        )

    def add_tag_filter_arguments(self, parser):
        parser.add_argument(
            "--include-tag",
            action="append",
            default=[],
            help="Datamailer tag to include. May be used more than once.",
        )
        parser.add_argument(
            "--exclude-tag",
            action="append",
            default=[],
            help="Datamailer tag to exclude. May be used more than once.",
        )

    def add_campaign_metadata_arguments(self, parser):
        parser.add_argument(
            "--category-tag",
            default="course-updates",
            help="Datamailer preference category for this campaign.",
        )
        parser.add_argument(
            "--recipient-list-key",
            default="",
            help="Optional Datamailer recipient-list key to target.",
        )
        parser.add_argument(
            "--metadata",
            action="append",
            default=[],
            help="Campaign metadata as key=value. May be used more than once.",
        )
        parser.add_argument(
            "--scheduled-at",
            default="",
            help="Optional ISO timestamp for scheduled delivery.",
        )

    def add_action_arguments(self, parser):
        parser.add_argument(
            "--queue",
            action="store_true",
            help="Queue the campaign after upserting it.",
        )
        parser.add_argument(
            "--cancel",
            action="store_true",
            help="Cancel the campaign after upserting it.",
        )
        parser.add_argument(
            "--preview",
            action="store_true",
            help="Render a Datamailer preview after upserting it.",
        )
        parser.add_argument(
            "--test-send",
            action="append",
            default=[],
            help=(
                "Send a Datamailer campaign test email. May be used more "
                "than once."
            ),
        )

    def add_output_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print raw Datamailer responses as JSON.",
        )

    def handle(self, *args, **options):
        self.validate_requested_actions(options)
        config = self.datamailer_config()
        client = DatamailerClient(config)
        external_key = options["external_key"]

        try:
            responses = self.run_campaign_requests(
                client,
                external_key,
                options,
            )
        except requests.RequestException as exc:
            if config.strict:
                raise
            self.raise_campaign_request_error(exc)

        self.write_responses(
            external_key,
            responses,
            raw_json=options["json"],
        )

    def validate_requested_actions(self, options):
        if options["queue"] and options["cancel"]:
            raise CommandError("--queue and --cancel cannot be used together.")

    def datamailer_config(self):
        config = DatamailerConfig.from_settings()
        if config is None:
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
            )
        return config

    def run_campaign_requests(self, client, external_key, options):
        payload = campaign_payload(options)
        upsert_response = client.upsert_campaign(
            external_key,
            payload,
        )
        responses = {
            "upsert": upsert_response
        }
        action_responses = self.run_campaign_actions(
            client,
            external_key,
            options,
        )
        responses.update(action_responses)
        return responses

    def run_campaign_actions(self, client, external_key, options):
        responses = {}
        if options["preview"]:
            responses["preview"] = client.preview_campaign(external_key)
        if options["test_send"]:
            responses["test_send"] = client.test_send_campaign(
                external_key,
                options["test_send"],
            )
        if options["queue"]:
            responses["queue"] = client.queue_campaign(external_key)
        if options["cancel"]:
            responses["cancel"] = client.cancel_campaign(external_key)
        return responses

    def raise_campaign_request_error(self, exc):
        raise CommandError(
            f"Datamailer campaign request failed: {exc}"
        ) from exc

    def write_responses(self, external_key, responses, *, raw_json):
        if raw_json:
            response_json = json.dumps(
                responses,
                indent=2,
                sort_keys=True,
            )
            self.stdout.write(response_json)
            return

        self.write_summary(external_key, responses)

    def write_summary(self, external_key, responses):
        campaign = (responses["upsert"] or {}).get("campaign", {})
        status = campaign.get("status", "unknown")
        self.stdout.write(f"Upserted {external_key}: status={status}")
        actions = ("preview", "test_send", "queue", "cancel")
        for action in actions:
            if action in responses:
                self.stdout.write(f"{action}: ok")
