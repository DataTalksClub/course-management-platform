"""Push CMP's transactional email templates into Datamailer.

Datamailer is client-agnostic and only stores/renders templates a client
sends it. CMP owns its template content (``course_management.transactional_templates``)
and publishes it through the generic Datamailer template API.

    uv run python manage.py upsert_datamailer_templates
    uv run python manage.py upsert_datamailer_templates --template-key peer-review-assignment
"""

import json

from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer import DatamailerClient, DatamailerConfig
from course_management.datamailer_templates import TEMPLATES


class Command(BaseCommand):
    help = "Create or update CMP's transactional templates in Datamailer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--template-key",
            choices=sorted(TEMPLATES),
            default="",
            help="Only upsert this template (default: all CMP templates).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print the raw Datamailer responses as JSON.",
        )

    def handle(self, *args, **options):
        config = DatamailerConfig.from_settings()
        if config is None:
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
            )

        client = DatamailerClient(config)
        keys = (
            [options["template_key"]]
            if options["template_key"]
            else sorted(TEMPLATES)
        )

        results = []
        for key in keys:
            response = client.request(
                "PUT",
                f"/api/transactional/templates/{key}",
                json=TEMPLATES[key],
            )
            result = {"template_key": key, "response": response}
            results.append(result)
            self.stdout.write(
                self.style.SUCCESS(f"upserted {key} -> {config.url}")
            )

        if options["json"]:
            self.stdout.write(json.dumps(results, indent=2, default=str))
