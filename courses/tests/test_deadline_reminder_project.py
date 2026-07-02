from unittest.mock import patch

from django.test import override_settings

from courses.tests.deadline_reminder_base import (
    DATAMAILER_SETTINGS,
    DeadlineReminderTestBase,
)
from courses.tests.deadline_reminder_project import (
    assert_project_reminder_payloads,
    create_project_submission_reminder_fixture,
)


class ProjectSubmissionDeadlineReminderCommandTest(DeadlineReminderTestBase):
    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListSendClient.send_to_transient_list"
    )
    def test_project_deadline_reminders_use_7d_and_24h_windows(
        self,
        send_transient,
        ):
        now = self.reminder_run_time()
        send_transient.return_value = {"enqueued_count": 1}
        create_project_submission_reminder_fixture(self, now)

        self.run_deadline_reminders(now)

        assert_project_reminder_payloads(self, send_transient)
