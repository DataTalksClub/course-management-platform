from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from courses.tests.datamailer_outbox_base import (
    DATAMAILER_SETTINGS,
    DatamailerOutboxTestBase,
)


class DatamailerOutboxStatusCommandTest(DatamailerOutboxTestBase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_datamailer_outbox_status_reports_counts_and_last_error(
        self,
        upsert_contact,
        upsert_member,
    ):
        event, _user = self.create_retrying_enrollment_outbox_event(upsert_member)
        event.next_attempt_at = timezone.now() - timedelta(seconds=1)
        event.save(update_fields=["next_attempt_at"])

        out = StringIO()
        call_command("datamailer_outbox_status", stdout=out)

        output = out.getvalue()
        self.assertIn("retrying: 1", output)
        self.assertIn("due: 1", output)
        self.assertIn(event.event_id, output)
        self.assertIn("last_successful_run: none", output)
        self.assertIn("last_datamailer_error:", output)
        self.assertIn("network error", output)


class DatamailerSendStatusCommandTest(DatamailerOutboxTestBase):
    def test_datamailer_send_status_reports_counts_and_failures(self):
        self.create_successful_send_audit()
        self.create_failed_send_audit()

        out = StringIO()
        call_command("datamailer_send_status", stdout=out)

        output = out.getvalue()
        self.assertIn("Datamailer send status", output)
        self.assertIn("total_sends: 2", output)
        self.assertIn("succeeded: 1", output)
        self.assertIn("failed: 1", output)
        self.assertIn("intended: 4", output)
        self.assertIn("enqueued: 1", output)
        self.assertIn("deadline-reminders: 1", output)
        self.assertIn("recent_failures:", output)
        self.assertIn("deadline-reminder", output)
        self.assertIn("network error", output)
