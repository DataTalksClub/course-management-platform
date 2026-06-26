from django.core.management.base import BaseCommand

from course_management.datamailer_outbox import process_due_datamailer_outbox


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
        result = process_due_datamailer_outbox(limit=options["limit"])
        self.stdout.write(
            "Processed {processed} Datamailer outbox event(s): "
            "{acked} acked, {retrying} retrying, {failed} failed.".format(
                **result
            )
        )
