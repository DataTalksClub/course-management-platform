"""Push CMP's transactional email templates into Datamailer.

Datamailer is client-agnostic and only stores/renders templates a client
sends it. CMP owns its template content (``course_management.transactional_templates``)
and publishes it through the generic Datamailer template API.

    uv run python manage.py upsert_datamailer_templates
    uv run python manage.py upsert_datamailer_templates --template-key peer-review-assignment
"""

import json

from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
    DatamailerRequestData,
)
from course_management.datamailer_templates.registry import TEMPLATES


def selected_template_keys(template_key):
    if template_key:
        return [template_key]
    return sorted(TEMPLATES)


def upsert_datamailer_templates(client, keys):
    results = []
    for key in keys:
        request_data = DatamailerRequestData(
            method="PUT",
            path=f"/api/transactional/templates/{key}",
            json=TEMPLATES[key],
        )
        response = client.request(request_data)
        result = {"template_key": key, "response": response}
        results.append(result)
    return results


class Command(BaseCommand):
    help = "Create or update CMP's transactional templates in Datamailer."

    def add_arguments(self, parser):
        template_choices = sorted(TEMPLATES)
        parser.add_argument(
            "--template-key",
            choices=template_choices,
            default="",
            help="Only upsert this template (default: all CMP templates).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print the raw Datamailer responses as JSON.",
        )

    def handle(self, *args, **options):
        config = self.get_datamailer_config()
        client = DatamailerClient(config)
        keys = selected_template_keys(options["template_key"])
        results = upsert_datamailer_templates(client, keys)

        self.write_upsert_results(config, results)
        if options["json"]:
            self.write_json_results(results)

    def get_datamailer_config(self):
        config = DatamailerConfig.from_settings()
        if config is None:
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
            )
        return config

    def write_upsert_results(self, config, results):
        for result in results:
            template_key = result["template_key"]
            message = self.style.SUCCESS(
                f"upserted {template_key} -> {config.url}"
            )
            self.stdout.write(message)

    def write_json_results(self, results):
        results_json = json.dumps(results, indent=2, default=str)
        self.stdout.write(results_json)
