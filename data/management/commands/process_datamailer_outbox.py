from django.core.management.base import BaseCommand, CommandError
from course_management.datamailer.client import DatamailerConfig

from course_management.datamailer_outbox_runs import (
    process_due_datamailer_outbox,
)
from course_management.relay.application_notifications import (
    process_application_notifications,
)
from course_management.relay.registration_digest import (
    maybe_send_scheduled_digest,
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
        # Application notifications have their own durable Relay-only queue.
        # Process even with missing configuration so failures remain visible.
        process_application_notifications(limit=options["limit"])
        # Daily registration digest piggybacks on this minutely schedule:
        # it sends at most once per Europe/Berlin day around 09:00 and never
        # raises, so digest trouble cannot block outbox processing.
        maybe_send_scheduled_digest()
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
