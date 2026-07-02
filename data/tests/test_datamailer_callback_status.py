from io import StringIO

from django.core.management import call_command
from django.test import override_settings

from .datamailer_webhook_base import DatamailerWebhookTestBase


class DatamailerCallbackStatusCommandTest(DatamailerWebhookTestBase):
    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_callback_status_command_reports_counts_and_duplicates(self):
        failed_payload = {
            "event_id": "evt-1",
            "event_type": "transactional.failed",
            "email": "student@example.com",
            "metadata": {"reason": "ses_permanent_failure"},
        }
        self.post_event(failed_payload)
        self.post_event(failed_payload)
        unsubscribe_payload = {
            "event_id": "evt-2",
            "event_type": "subscription.unsubscribed",
            "email": "student@example.com",
            "preference_key": "email_course_updates",
        }
        self.post_event(unsubscribe_payload)

        out = StringIO()
        call_command("datamailer_callback_status", stdout=out)

        output = out.getvalue()
        self.assertIn("total_events: 2", output)
        self.assertIn("duplicate_callbacks: 1", output)
        self.assertIn("transactional.failed: 1 (duplicates=1)", output)
        self.assertIn("subscription.unsubscribed: 1 (duplicates=0)", output)
