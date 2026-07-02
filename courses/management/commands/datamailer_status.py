from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer.client import (
    datamailer_enabled,
)
from course_management.datamailer.status_output import DatamailerStatusWriter
from course_management.datamailer.sync.status import (
    get_email_status,
    get_transactional_message_status,
)


class Command(BaseCommand):
    help = "Look up Datamailer contact sendability and recent send history."

    def add_arguments(self, parser):
        parser.add_argument("email", nargs="?")
        parser.add_argument(
            "--message-id",
            type=int,
            help="Look up one transactional message by Datamailer message id.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Number of recent history items to request per history type.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print the raw Datamailer response as JSON.",
        )

    def handle(self, *args, **options):
        if not datamailer_enabled():
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
            )

        writer = DatamailerStatusWriter(self.stdout)

        if options["message_id"]:
            result = self.message_status_result(options["message_id"])
            writer.write_message_status_result(
                result,
                raw_json=options["json"],
            )
            return

        if not options["email"]:
            raise CommandError("Provide an email or --message-id.")

        result = self.email_status_result(options)
        writer.write_email_status(
            result,
            raw_json=options["json"],
        )

    def message_status_result(self, message_id):
        result = get_transactional_message_status(message_id)
        if result is None:
            raise CommandError("Datamailer message status lookup failed.")
        return result

    def email_status_result(self, options):
        result = get_email_status(options["email"], limit=options["limit"])
        if result is None:
            raise CommandError("Datamailer status lookup failed.")
        return result
