import json

from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer.client import (
    datamailer_enabled,
)
from course_management.datamailer.sync import (
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

        if options["message_id"]:
            result = self.message_status_result(options["message_id"])
            self.print_message_status(
                result,
                raw_json=options["json"],
            )
            return

        if not options["email"]:
            raise CommandError("Provide an email or --message-id.")

        result = self.email_status_result(options)
        self.print_email_status(
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

    def write_raw_json(self, result):
        result_json = json.dumps(result, indent=2, sort_keys=True)
        self.stdout.write(result_json)

    def print_email_status(self, result, *, raw_json):
        if raw_json:
            self.write_raw_json(result)
            return

        status = result["status"]
        history = result.get("history") or {}

        self.write_contact_status(status)

        if not status.get("contact_id"):
            return

        transactional_messages = history.get("transactional_messages", [])
        self.write_history_section(
            "Recent transactional messages:",
            transactional_messages,
            self.transactional_message_line,
        )
        campaign_recipients = history.get("campaign_recipients", [])
        self.write_history_section(
            "Recent campaign recipients:",
            campaign_recipients,
            self.campaign_recipient_line,
        )

    def write_contact_status(self, status):
        fields = [
            ("Email", status["email"]),
            ("Exists", status["exists"]),
            ("Contact ID", status["contact_id"] or "-"),
            ("Can send marketing", status["can_send_marketing"]),
            ("Can send transactional", status["can_send_transactional"]),
            ("Client status", status["client"]["status"] or "-"),
            ("Client verified", status["client"]["verified"]),
            ("Hard bounced", status["hard_bounced"]),
            ("Complained", status["complained"]),
        ]
        for label, value in fields:
            self.stdout.write(f"{label}: {value}")

    def write_history_section(self, title, items, line_formatter):
        self.stdout.write("")
        self.stdout.write(title)
        if not items:
            self.stdout.write("  none")
            return
        for item in items:
            line = line_formatter(item)
            self.stdout.write(line)

    def transactional_message_line(self, message):
        sent_at = message["sent_at"] or "-"
        delivered_at = message["delivered_at"] or "-"
        last_error = message["last_error"] or "-"
        return (
            "  "
            f"{message['id']} {message['template_key']} "
            f"{message['status']} sent={sent_at} "
            f"delivered={delivered_at} "
            f"error={last_error}"
        )

    def campaign_recipient_line(self, recipient):
        sent_at = recipient["sent_at"] or "-"
        delivered_at = recipient["delivered_at"] or "-"
        last_error = recipient["last_error"] or "-"
        return (
            "  "
            f"{recipient['id']} {recipient['campaign']['subject']} "
            f"{recipient['status']} sent={sent_at} "
            f"delivered={delivered_at} "
            f"error={last_error}"
        )

    def print_message_status(self, result, *, raw_json):
        if raw_json:
            self.write_raw_json(result)
            return

        message = result["message"]
        self.write_message_status(message)
        events = result.get("events", [])
        self.write_message_events(events)

    def display_value(self, value):
        if value:
            return value
        return "-"

    def message_status_fields(self, message):
        return [
            ("Message ID", message["id"]),
            ("Email", message["email"]),
            ("Template", message["template_key"]),
            ("Status", message["status"]),
            ("Queued/created", message["created_at"]),
            ("Sent", self.display_value(message["sent_at"])),
            ("Delivered", self.display_value(message["delivered_at"])),
            ("Opened", self.display_value(message["first_opened_at"])),
            ("Clicked", self.display_value(message["first_clicked_at"])),
            ("Last error", self.display_value(message["last_error"])),
        ]

    def write_message_status(self, message):
        fields = self.message_status_fields(message)
        for label, value in fields:
            self.stdout.write(f"{label}: {value}")

    def write_message_events(self, events):
        self.stdout.write("")
        self.stdout.write("Events:")
        if not events:
            self.stdout.write("  none")
            return
        for event in events:
            line = (
                "  "
                f"{event['id']} {event['event_type']} "
                f"at={event['created_at']}"
            )
            self.stdout.write(line)
