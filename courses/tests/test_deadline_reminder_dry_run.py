from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.test import override_settings

from courses.models import Homework
from courses.tests.deadline_reminder_base import (
    DATAMAILER_SETTINGS,
    DeadlineReminderTestBase,
)


class DeadlineReminderDryRunCommandTest(DeadlineReminderTestBase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListSendClient.send_to_transient_list"
    )
    def test_deadline_reminder_dry_run_does_not_call_datamailer(
        self,
        send_transient,
    ):
        now = self.reminder_run_time()
        course = self.create_course()
        user = self.create_user("student", "student@example.com")
        self.create_enrollment(user, course)
        Homework.objects.create(
            course=course,
            slug="homework-1",
            title="Homework 1",
            due_date=now + timedelta(days=1, hours=14),
        )

        out = StringIO()
        self.run_deadline_reminders(now, stdout=out, dry_run=True)
        output = out.getvalue()

        self.assertIn(
            "deadline-reminders:homework:ml-zoomcamp-2026:homework-1:24h: 1 member(s)",
            output,
        )
        send_transient.assert_not_called()
