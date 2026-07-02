from io import StringIO
from unittest.mock import patch

from django.test import override_settings

from courses.tests.deadline_reminder_base import (
    DATAMAILER_SETTINGS,
    DeadlineReminderTestBase,
)
from courses.tests.deadline_reminder_homework import (
    HomeworkReminderTestMixin,
)


class HomeworkDeadlineReminderCommandTest(
    HomeworkReminderTestMixin,
    DeadlineReminderTestBase,
):
    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListSendClient.send_to_transient_list"
    )
    def test_homework_deadline_reminder_sends_transient_eligible_learners(
        self,
        send_transient,
    ):
        now = self.reminder_run_time()
        send_transient.return_value = {"enqueued_count": 1}
        fixture = self.create_homework_reminder_fixture(now)

        out = StringIO()
        self.run_deadline_reminders(now, stdout=out)
        output = out.getvalue()

        self.assertIn(
            "Prepared 1 reminder event(s), 2 member(s).",
            output,
        )
        send_transient.assert_called_once()
        payload = send_transient.call_args.args[0]
        self.assert_homework_reminder_payload(
            payload,
            fixture,
        )
        self.assert_homework_reminder_audit(fixture.homework)
