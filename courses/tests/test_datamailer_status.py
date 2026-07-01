from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import CustomUser
from course_management.datamailer.preferences import (
    get_email_preferences_for_user,
    update_email_preferences_for_user,
)
from course_management.datamailer.sync.status import (
    get_contact_history,
    get_contact_status,
    get_email_status,
    get_transactional_message_status,
)


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


class DatamailerStatusTest(TestCase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.contact_status"
    )
    def test_get_contact_status_uses_datamailer_client(
        self, contact_status
    ):
        contact_status.return_value = {"exists": True}

        result = get_contact_status("student@example.com")

        self.assertEqual(result, {"exists": True})
        contact_status.assert_called_once_with("student@example.com")

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.contact_history"
    )
    def test_get_contact_history_uses_datamailer_client(
        self, contact_history
    ):
        contact_history.return_value = {"transactional_messages": []}

        result = get_contact_history(42, limit=5)

        self.assertEqual(result, {"transactional_messages": []})
        contact_history.assert_called_once_with(42, limit=5)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.sync.status.get_contact_history")
    @patch("course_management.datamailer.sync.status.get_contact_status")
    def test_get_email_status_combines_status_and_history(
        self,
        contact_status,
        contact_history,
    ):
        contact_status.return_value = {
            "contact_id": 42,
            "email": "student@example.com",
        }
        contact_history.return_value = {"transactional_messages": []}

        result = get_email_status("student@example.com", limit=5)

        self.assertEqual(
            result,
            {
                "status": {
                    "contact_id": 42,
                    "email": "student@example.com",
                },
                "history": {"transactional_messages": []},
            },
        )
        contact_status.assert_called_once_with("student@example.com")
        contact_history.assert_called_once_with(42, limit=5)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.contact_preferences"
    )
    def test_get_email_preferences_for_user_reads_datamailer_categories(
        self,
        contact_preferences,
    ):
        contact_preferences.return_value = {
            "categories": [
                {"tag": "submission-results", "enabled": False},
                {"tag": "deadline-reminders", "enabled": True},
                {"tag": "course-updates", "enabled": False},
            ]
        }
        user = CustomUser.objects.create_user(
            username="student",
            email="Student@Example.com",
        )

        result = get_email_preferences_for_user(user)

        self.assertEqual(
            result,
            {
                "email_submission_confirmations": False,
                "email_deadline_reminders": True,
                "email_course_updates": False,
            },
        )
        contact_preferences.assert_called_once_with(
            "student@example.com",
            category_tags=[
                "submission-results",
                "deadline-reminders",
                "course-updates",
            ],
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.update_contact_preferences"
    )
    def test_update_email_preferences_for_user_writes_datamailer_categories(
        self,
        update_contact_preferences,
    ):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
        )

        result = update_email_preferences_for_user(
            user,
            {
                "email_submission_confirmations": False,
                "email_course_updates": True,
            },
        )

        self.assertTrue(result)
        update_contact_preferences.assert_called_once_with(
            "student@example.com",
            [
                {
                    "tag": "submission-results",
                    "label": "Homework and project submissions",
                    "enabled": False,
                },
                {
                    "tag": "course-updates",
                    "label": "General course-related emails",
                    "enabled": True,
                },
            ],
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.transactional_message_status"
    )
    def test_get_transactional_message_status_uses_datamailer_client(
        self,
        message_status,
    ):
        message_status.return_value = {"message": {"id": 42}}

        result = get_transactional_message_status(42)

        self.assertEqual(result, {"message": {"id": 42}})
        message_status.assert_called_once_with(42)

    def email_status_response(self):
        return {
            "status": {
                "email": "student@example.com",
                "exists": True,
                "contact_id": 42,
                "can_send_marketing": True,
                "can_send_transactional": True,
                "client": {"status": "subscribed", "verified": True},
                "hard_bounced": False,
                "complained": False,
            },
            "history": {
                "transactional_messages": [
                    {
                        "id": 7,
                        "template_key": "welcome",
                        "status": "sent",
                        "sent_at": "2026-01-01T00:00:00Z",
                        "delivered_at": None,
                        "last_error": "",
                    }
                ],
                "campaign_recipients": [],
            },
        }

    def run_datamailer_status_command(self, *args):
        out = StringIO()
        call_command("datamailer_status", *args, stdout=out)
        return out.getvalue()

    def assert_email_history_output(self, output):
        self.assertIn("Email: student@example.com", output)
        self.assertIn("Recent transactional messages:", output)
        self.assertIn("7 welcome sent", output)
        self.assertIn("Recent campaign recipients:\n  none", output)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.management.commands.datamailer_status.get_email_status")
    def test_datamailer_status_command_prints_email_history(
        self,
        get_status,
    ):
        get_status.return_value = self.email_status_response()

        output = self.run_datamailer_status_command("student@example.com")

        self.assert_email_history_output(output)
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
        get_message_status.return_value = {
            "message": {
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
            },
            "events": [
                {
                    "id": 99,
                    "event_type": "sent",
                    "created_at": "2026-01-01T00:01:00Z",
                }
            ],
        }

        out = StringIO()
        call_command("datamailer_status", "--message-id", "42", stdout=out)

        output = out.getvalue()
        self.assertIn("Message ID: 42", output)
        self.assertIn("Events:", output)
        self.assertIn("99 sent at=2026-01-01T00:01:00Z", output)
        get_message_status.assert_called_once_with(42)
