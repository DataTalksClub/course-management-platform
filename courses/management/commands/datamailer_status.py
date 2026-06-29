import json

from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer import (
    datamailer_enabled,
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
            result = get_transactional_message_status(options["message_id"])
            if result is None:
                raise CommandError("Datamailer message status lookup failed.")
            self.print_message_status(result, raw_json=options["json"])
            return

        if not options["email"]:
            raise CommandError("Provide an email or --message-id.")

        result = get_email_status(options["email"], limit=options["limit"])
        if result is None:
            raise CommandError("Datamailer status lookup failed.")

        self.print_email_status(result, raw_json=options["json"])

    def write_raw_json(self, result):
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))

    def print_email_status(self, result, *, raw_json):
        if raw_json:
            self.write_raw_json(result)
            return

        status = result["status"]
        history = result.get("history") or {}

        self.write_contact_status(status)

        if not status.get("contact_id"):
            return

        self.write_history_section(
            "Recent transactional messages:",
            history.get("transactional_messages", []),
            self.transactional_message_line,
        )
        self.write_history_section(
            "Recent campaign recipients:",
            history.get("campaign_recipients", []),
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
            self.stdout.write(line_formatter(item))

    def transactional_message_line(self, message):
        return (
            "  "
            f"{message['id']} {message['template_key']} "
            f"{message['status']} sent={message['sent_at'] or '-'} "
            f"delivered={message['delivered_at'] or '-'} "
            f"error={message['last_error'] or '-'}"
        )

    def campaign_recipient_line(self, recipient):
        return (
            "  "
            f"{recipient['id']} {recipient['campaign']['subject']} "
            f"{recipient['status']} sent={recipient['sent_at'] or '-'} "
            f"delivered={recipient['delivered_at'] or '-'} "
            f"error={recipient['last_error'] or '-'}"
        )

    def print_message_status(self, result, *, raw_json):
        if raw_json:
            self.write_raw_json(result)
            return

        message = result["message"]
        self.write_message_status(message)
        self.write_message_events(result.get("events", []))

    def write_message_status(self, message):
        fields = [
            ("Message ID", message["id"]),
            ("Email", message["email"]),
            ("Template", message["template_key"]),
            ("Status", message["status"]),
            ("Queued/created", message["created_at"]),
            ("Sent", message["sent_at"] or "-"),
            ("Delivered", message["delivered_at"] or "-"),
            ("Opened", message["first_opened_at"] or "-"),
            ("Clicked", message["first_clicked_at"] or "-"),
            ("Last error", message["last_error"] or "-"),
        ]
        for label, value in fields:
            self.stdout.write(f"{label}: {value}")

    def write_message_events(self, events):
        self.stdout.write("")
        self.stdout.write("Events:")
        if not events:
            self.stdout.write("  none")
            return
        for event in events:
            self.stdout.write(
                "  "
                f"{event['id']} {event['event_type']} "
                f"at={event['created_at']}"
            )
