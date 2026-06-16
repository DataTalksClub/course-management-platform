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

        if options["json"]:
            self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
            return

        status = result["status"]
        history = result.get("history") or {}

        self.stdout.write(f"Email: {status['email']}")
        self.stdout.write(f"Exists: {status['exists']}")
        self.stdout.write(f"Contact ID: {status['contact_id'] or '-'}")
        self.stdout.write(f"Can send marketing: {status['can_send_marketing']}")
        self.stdout.write(f"Can send transactional: {status['can_send_transactional']}")
        self.stdout.write(f"Client status: {status['client']['status'] or '-'}")
        self.stdout.write(f"Client verified: {status['client']['verified']}")
        self.stdout.write(f"Hard bounced: {status['hard_bounced']}")
        self.stdout.write(f"Complained: {status['complained']}")

        if not status.get("contact_id"):
            return

        self.stdout.write("")
        self.stdout.write("Recent transactional messages:")
        transactional_messages = history.get("transactional_messages", [])
        if not transactional_messages:
            self.stdout.write("  none")
        for message in transactional_messages:
            self.stdout.write(
                "  "
                f"{message['id']} {message['template_key']} "
                f"{message['status']} sent={message['sent_at'] or '-'} "
                f"delivered={message['delivered_at'] or '-'} "
                f"error={message['last_error'] or '-'}"
            )

        self.stdout.write("")
        self.stdout.write("Recent campaign recipients:")
        campaign_recipients = history.get("campaign_recipients", [])
        if not campaign_recipients:
            self.stdout.write("  none")
        for recipient in campaign_recipients:
            self.stdout.write(
                "  "
                f"{recipient['id']} {recipient['campaign']['subject']} "
                f"{recipient['status']} sent={recipient['sent_at'] or '-'} "
                f"delivered={recipient['delivered_at'] or '-'} "
                f"error={recipient['last_error'] or '-'}"
            )

    def print_message_status(self, result, *, raw_json):
        if raw_json:
            self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
            return

        message = result["message"]
        self.stdout.write(f"Message ID: {message['id']}")
        self.stdout.write(f"Email: {message['email']}")
        self.stdout.write(f"Template: {message['template_key']}")
        self.stdout.write(f"Status: {message['status']}")
        self.stdout.write(f"Queued/created: {message['created_at']}")
        self.stdout.write(f"Sent: {message['sent_at'] or '-'}")
        self.stdout.write(f"Delivered: {message['delivered_at'] or '-'}")
        self.stdout.write(f"Opened: {message['first_opened_at'] or '-'}")
        self.stdout.write(f"Clicked: {message['first_clicked_at'] or '-'}")
        self.stdout.write(f"Last error: {message['last_error'] or '-'}")

        self.stdout.write("")
        self.stdout.write("Events:")
        if not result.get("events"):
            self.stdout.write("  none")
        for event in result.get("events", []):
            self.stdout.write(
                "  "
                f"{event['id']} {event['event_type']} "
                f"at={event['created_at']}"
            )
