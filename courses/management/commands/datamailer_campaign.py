import json
from pathlib import Path

import requests
from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer import DatamailerClient, DatamailerConfig


def read_body(*, inline="", file_path=""):
    if inline and file_path:
        raise CommandError(
            "Provide either inline body text or a body file, not both."
        )
    if file_path:
        return Path(file_path).read_text(encoding="utf-8")
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


def campaign_payload(options):
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

    subject = options["subject"].strip()
    if not subject:
        raise CommandError("--subject is required.")
    category_tag = options["category_tag"].strip()
    if not category_tag:
        raise CommandError("--category-tag is required.")

    payload = {
        "subject": subject,
        "preview_text": options["preview_text"],
        "html_body": html_body,
        "text_body": text_body,
        "category_tag": category_tag,
        "include_tags": options["include_tag"],
        "exclude_tags": options["exclude_tag"],
        "metadata": parse_metadata(options["metadata"]),
    }
    if options["scheduled_at"]:
        payload["scheduled_at"] = options["scheduled_at"]
    return payload


class Command(BaseCommand):
    help = "Create/update and optionally operate a Datamailer campaign."

    def add_arguments(self, parser):
        parser.add_argument("external_key", help="Stable external campaign key.")
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
        parser.add_argument(
            "--category-tag",
            default="course-updates",
            help="Datamailer preference category for this campaign.",
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
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print raw Datamailer responses as JSON.",
        )

    def handle(self, *args, **options):
        if options["queue"] and options["cancel"]:
            raise CommandError("--queue and --cancel cannot be used together.")

        config = DatamailerConfig.from_settings()
        if config is None:
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
            )

        client = DatamailerClient(config)
        responses = {}
        external_key = options["external_key"]
        try:
            responses["upsert"] = client.upsert_campaign(
                external_key,
                campaign_payload(options),
            )
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
        except requests.RequestException as exc:
            if config.strict:
                raise
            raise CommandError(
                f"Datamailer campaign request failed: {exc}"
            ) from exc

        if options["json"]:
            self.stdout.write(json.dumps(responses, indent=2, sort_keys=True))
            return

        campaign = (responses["upsert"] or {}).get("campaign", {})
        status = campaign.get("status", "unknown")
        self.stdout.write(f"Upserted {external_key}: status={status}")
        for action in ("preview", "test_send", "queue", "cancel"):
            if action in responses:
                self.stdout.write(f"{action}: ok")
