from io import StringIO
from unittest.mock import patch

import requests
from django.core.management import call_command
from django.test import override_settings

from data.models import DatamailerOutboxStatus
from course_management.datamailer.sync.memberships import (
    sync_enrollment_to_datamailer,
)
from courses.tests.datamailer_outbox_base import (
    DATAMAILER_SETTINGS,
    DatamailerOutboxTestBase,
)


class DatamailerOutboxMembershipTest(DatamailerOutboxTestBase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.upsert"
    )
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.upsert_contact"
    )
    def test_membership_sync_failure_records_retryable_outbox_event(
        self,
        upsert_contact,
        upsert_member,
    ):
        event, user = self.create_retrying_enrollment_outbox_event(upsert_member)

        self.assert_retrying_membership_outbox_event(event, user)


class DatamailerOutboxProcessingTest(DatamailerOutboxTestBase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.upsert"
    )
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.upsert_contact"
    )
    def test_process_datamailer_outbox_retries_due_events(
        self,
        upsert_contact,
        upsert_member,
    ):
        network_error = requests.RequestException("network error")
        successful_response = {"ok": True}
        upsert_member.side_effect = [
            network_error,
            successful_response,
        ]
        enrollment = self.create_student_enrollment_for_ml_course()
        sync_enrollment_to_datamailer(enrollment)
        self.process_due_outbox()
        event = self.mark_outbox_event_due()

        out = StringIO()
        call_command("process_datamailer_outbox", stdout=out)

        event.refresh_from_db()
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(event.attempt_count, 2)
        self.assertEqual(upsert_contact.call_count, 2)
        self.assertEqual(upsert_member.call_count, 2)
        output = out.getvalue()
        self.assertIn("1 acked", output)
        self.assert_successful_outbox_dispatch_run()
