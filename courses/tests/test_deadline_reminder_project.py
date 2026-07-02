from unittest.mock import patch

from django.test import override_settings

from courses.tests.deadline_reminder_base import (
    DATAMAILER_SETTINGS,
    DeadlineReminderTestBase,
)
from courses.tests.deadline_reminder_project import (
    ProjectSubmissionReminderTestMixin,
)


class ProjectSubmissionDeadlineReminderCommandTest(
    ProjectSubmissionReminderTestMixin,
    DeadlineReminderTestBase,
):
    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListClient.send_transient_recipient_list_transactional"
    )
    def test_project_deadline_reminders_use_7d_and_24h_windows(
        self,
        send_transient,
    ):
        now = self.reminder_run_time()
        send_transient.return_value = {"enqueued_count": 1}
        self.create_project_submission_reminder_fixture(now)

        self.run_deadline_reminders(now)

        self.assert_project_reminder_payloads(send_transient)
