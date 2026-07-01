import json

import requests
from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)
from course_management.datamailer.campaign_operations import (
    DatamailerCampaignRunData,
    run_campaign_requests,
)


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
            run_data = DatamailerCampaignRunData(
                client=client,
                external_key=external_key,
                options=options,
            )
            responses = run_campaign_requests(run_data)
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
        for action in ("preview", "test_send", "queue", "cancel"):
            if action in responses:
                self.stdout.write(f"{action}: ok")
