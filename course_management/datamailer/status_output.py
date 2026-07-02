import json


def display_value(value):
    if value:
        return value
    return "-"


def contact_status_fields(status):
    return (
        ("Email", status["email"]),
        ("Exists", status["exists"]),
        ("Contact ID", status["contact_id"] or "-"),
        ("Can send marketing", status["can_send_marketing"]),
        ("Can send transactional", status["can_send_transactional"]),
        ("Client status", status["client"]["status"] or "-"),
        ("Client verified", status["client"]["verified"]),
        ("Hard bounced", status["hard_bounced"]),
        ("Complained", status["complained"]),
    )


def transactional_message_line(message):
    sent_at = display_value(message["sent_at"])
    delivered_at = display_value(message["delivered_at"])
    last_error = display_value(message["last_error"])
    return (
        "  "
        f"{message['id']} {message['template_key']} "
        f"{message['status']} sent={sent_at} "
        f"delivered={delivered_at} "
        f"error={last_error}"
    )


def campaign_recipient_line(recipient):
    sent_at = display_value(recipient["sent_at"])
    delivered_at = display_value(recipient["delivered_at"])
    last_error = display_value(recipient["last_error"])
    return (
        "  "
        f"{recipient['id']} {recipient['campaign']['subject']} "
        f"{recipient['status']} sent={sent_at} "
        f"delivered={delivered_at} "
        f"error={last_error}"
    )


def message_status_fields(message):
    sent_at = display_value(message["sent_at"])
    delivered_at = display_value(message["delivered_at"])
    first_opened_at = display_value(message["first_opened_at"])
    first_clicked_at = display_value(message["first_clicked_at"])
    last_error = display_value(message["last_error"])

    return (
        ("Message ID", message["id"]),
        ("Email", message["email"]),
        ("Template", message["template_key"]),
        ("Status", message["status"]),
        ("Queued/created", message["created_at"]),
        ("Sent", sent_at),
        ("Delivered", delivered_at),
        ("Opened", first_opened_at),
        ("Clicked", first_clicked_at),
        ("Last error", last_error),
    )


def message_event_line(event):
    return (
        "  "
        f"{event['id']} {event['event_type']} "
        f"at={event['created_at']}"
    )


class DatamailerStatusWriter:
    def __init__(self, stdout):
        self.stdout = stdout

    def write_raw_json(self, result):
        result_json = json.dumps(result, indent=2, sort_keys=True)
        self.stdout.write(result_json)

    def write_email_status(self, result, *, raw_json):
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
            transactional_message_line,
        )
        campaign_recipients = history.get("campaign_recipients", [])
        self.write_history_section(
            "Recent campaign recipients:",
            campaign_recipients,
            campaign_recipient_line,
        )

    def write_contact_status(self, status):
        fields = contact_status_fields(status)
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

    def write_message_status_result(self, result, *, raw_json):
        if raw_json:
            self.write_raw_json(result)
            return

        message = result["message"]
        self.write_message_status(message)
        events = result.get("events", [])
        self.write_message_events(events)

    def write_message_status(self, message):
        fields = message_status_fields(message)
        for label, value in fields:
            self.stdout.write(f"{label}: {value}")

    def write_message_events(self, events):
        self.stdout.write("")
        self.stdout.write("Events:")
        if not events:
            self.stdout.write("  none")
            return
        for event in events:
            line = message_event_line(event)
            self.stdout.write(line)
