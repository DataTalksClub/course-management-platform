from django.core.management.base import BaseCommand, CommandError
from course_management.datamailer.client import DatamailerConfig

from course_management.datamailer_outbox_runs import (
    process_due_datamailer_outbox,
)


class Command(BaseCommand):
    help = "Dispatch pending/retrying Datamailer outbox events."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum number of due events to process.",
        )

    def handle(self, *args, **options):
        if DatamailerConfig.from_settings() is None:
            raise CommandError("Relay configuration missing; outbox preserved")
        result = process_due_datamailer_outbox(limit=options["limit"])
        message = (
            "Processed {processed} Datamailer outbox event(s): "
            "{acked} acked, {retrying} retrying, {failed} failed."
        ).format(
            **result
        )
        self.stdout.write(message)
