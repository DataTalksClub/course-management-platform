from django.core.management.base import BaseCommand, CommandError

from course_management.relay.application_templates import (
    TRANSACTIONAL_TEMPLATES,
)


class Command(BaseCommand):
    help = (
        "Validate registered transactional templates: every required "
        "placeholder has an example value, and (with --live) each template "
        "dry-run renders in Relay with those values."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--live",
            action="store_true",
            help="Dry-run render each template in Relay (needs Relay config).",
        )

    def handle(self, *args, **options):
        for key, spec in TRANSACTIONAL_TEMPLATES.items():
            missing = [
                field
                for field in spec["required_context"]
                if field not in spec["example_context"]
            ]
            if missing:
                raise CommandError(
                    f"Template {key} missing examples: {', '.join(missing)}"
                )
            if options["live"]:
                self.dry_run_template(key, spec)
            self.stdout.write(f"Checked {key}")
        self.stdout.write("All transactional templates checked.")

    def dry_run_template(self, key, spec):
        from course_management.relay.application_notifications import (
            relay_request,
        )

        try:
            relay_request(
                "POST",
                "/api/transactional/send",
                {
                    "client": "dtc-courses",
                    "audience": "dtc-courses",
                    "email": "preview@example.com",
                    "template_key": key,
                    "category_tag": "transactional",
                    "idempotency_key": f"template-check:{key}",
                    "context": spec["example_context"],
                    "metadata": {"source": "template-check"},
                    "dry_run": True,
                },
            )
        except Exception as exc:
            raise CommandError(
                f"Relay dry-run failed for {key}: {type(exc).__name__}"
            ) from None
