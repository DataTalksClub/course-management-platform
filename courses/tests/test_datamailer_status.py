from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from .datamailer_settings import DATAMAILER_SETTINGS


def run_datamailer_status_command(*args):
    out = StringIO()
    call_command("datamailer_status", *args, stdout=out)
    return out.getvalue()


class DatamailerStatusCommandTest(TestCase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.management.commands.datamailer_status.get_email_status")
    def test_datamailer_status_command_prints_email_history(
        self,
        get_status,
    ):
        message = {
            "id": 7,
            "template_key": "welcome",
            "status": "sent",
            "sent_at": "2026-01-01T00:00:00Z",
            "delivered_at": None,
            "last_error": "",
        }
        transactional_messages = []
        transactional_messages.append(message)
        history = {
            "transactional_messages": transactional_messages,
            "campaign_recipients": [],
        }
        status = {
            "email": "student@example.com",
            "exists": True,
            "contact_id": 42,
            "can_send_marketing": True,
            "can_send_transactional": True,
            "client": {"status": "subscribed", "verified": True},
            "hard_bounced": False,
            "complained": False,
        }
        get_status.return_value = {
            "status": status,
            "history": history,
        }

        output = run_datamailer_status_command("student@example.com")

        self.assertIn("Email: student@example.com", output)
        self.assertIn("Recent transactional messages:", output)
        self.assertIn("7 welcome sent", output)
        self.assertIn("Recent campaign recipients:\n  none", output)
        get_status.assert_called_once_with("student@example.com", limit=10)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "courses.management.commands.datamailer_status."
        "get_transactional_message_status"
    )
    def test_datamailer_status_command_prints_message_events(
        self,
        get_message_status,
    ):
        event = {
            "id": 99,
            "event_type": "sent",
            "created_at": "2026-01-01T00:01:00Z",
        }
        message = {
            "id": 42,
            "email": "student@example.com",
            "template_key": "welcome",
            "status": "sent",
            "created_at": "2026-01-01T00:00:00Z",
            "sent_at": "2026-01-01T00:01:00Z",
            "delivered_at": None,
            "first_opened_at": None,
            "first_clicked_at": None,
            "last_error": "",
        }
        events = []
        events.append(event)
        get_message_status.return_value = {
            "message": message,
            "events": events,
        }

        output = run_datamailer_status_command("--message-id", "42")

        self.assertIn("Message ID: 42", output)
        self.assertIn("Events:", output)
        self.assertIn("99 sent at=2026-01-01T00:01:00Z", output)
        get_message_status.assert_called_once_with(42)
