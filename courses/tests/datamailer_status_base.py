from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounts.models import CustomUser


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


class DatamailerUserTestBase(TestCase):
    def create_student_user(self, email="student@example.com"):
        return CustomUser.objects.create_user(
            username="student",
            email=email,
        )


class DatamailerPreferenceReadTestBase(DatamailerUserTestBase):
    def contact_preferences_response(self):
        categories = []
        submission_category = {
            "tag": "submission-results",
            "enabled": False,
        }
        categories.append(submission_category)
        deadline_category = {
            "tag": "deadline-reminders",
            "enabled": True,
        }
        categories.append(deadline_category)
        course_category = {
            "tag": "course-updates",
            "enabled": False,
        }
        categories.append(course_category)
        return {"categories": categories}

    def assert_datamailer_preferences(self, result):
        expected = {
            "email_submission_confirmations": False,
            "email_deadline_reminders": True,
            "email_course_updates": False,
        }
        self.assertEqual(result, expected)

    def assert_contact_preferences_read(self, contact_preferences):
        category_tags = []
        category_tags.append("submission-results")
        category_tags.append("deadline-reminders")
        category_tags.append("course-updates")
        contact_preferences.assert_called_once_with(
            "student@example.com",
            category_tags=category_tags,
        )


class DatamailerPreferenceUpdateTestBase(DatamailerUserTestBase):
    def updated_email_preferences(self):
        return {
            "email_submission_confirmations": False,
            "email_course_updates": True,
        }

    def expected_contact_preference_updates(self):
        preferences = []
        submission_preference = {
            "tag": "submission-results",
            "label": "Homework and project submissions",
            "enabled": False,
        }
        preferences.append(submission_preference)
        course_preference = {
            "tag": "course-updates",
            "label": "General course-related emails",
            "enabled": True,
        }
        preferences.append(course_preference)
        return preferences

    def assert_contact_preferences_updated(self, update_contact_preferences):
        expected_updates = self.expected_contact_preference_updates()
        update_contact_preferences.assert_called_once_with(
            "student@example.com",
            expected_updates,
        )


class DatamailerStatusCommandRunnerTestBase(TestCase):
    def run_datamailer_status_command(self, *args):
        out = StringIO()
        call_command("datamailer_status", *args, stdout=out)
        return out.getvalue()


class DatamailerEmailHistoryCommandTestBase:
    def email_status_response(self):
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
        return {
            "status": status,
            "history": history,
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


class DatamailerMessageStatusCommandTestBase:
    def message_status_response(self):
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
        return {
            "message": message,
            "events": events,
        }

    def assert_message_events_output(self, output):
        self.assertIn("Message ID: 42", output)
        self.assertIn("Events:", output)
        self.assertIn("99 sent at=2026-01-01T00:01:00Z", output)
