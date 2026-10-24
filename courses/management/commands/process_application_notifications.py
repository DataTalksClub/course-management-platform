from django.core.management.base import BaseCommand

from course_management.relay.application_notifications import (
    process_application_notifications,
)


class Command(BaseCommand):
    help = "Process the durable Relay application notification queue."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        count = process_application_notifications(limit=options["limit"])
        self.stdout.write(f"Processed {count} application notifications")
