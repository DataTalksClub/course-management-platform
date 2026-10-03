from datetime import timedelta
from io import StringIO

import requests
from django.core.management.base import CommandError
from django.test import override_settings
from unittest.mock import patch

from courses.models import Homework
from courses.tests.deadline_reminder_base import (
    RELAY_SETTINGS,
    DeadlineReminderTestBase,
)
from data.models import DatamailerSendAudit, DatamailerSendAuditStatus


SEND_TARGET = (
    "course_management.datamailer.client_recipient_lists."
    "DatamailerRecipientListSendClient.send_to_transient_list"
)


class DeadlineReminderFailureIsolationTest(DeadlineReminderTestBase):
    """A failing reminder must not cancel the reminders queued behind it.

    Production showed one audit row per run: the first event failed, the
    command aborted, and every later event was silently dropped.
    """

    def create_two_homeworks(self, course, now):
        first = Homework.objects.create(
            course=course,
            slug="homework-1",
            title="Homework 1",
            due_date=now + timedelta(days=1, hours=10),
        )
        second = Homework.objects.create(
            course=course,
            slug="homework-2",
            title="Homework 2",
            due_date=now + timedelta(days=1, hours=14),
        )
        return first, second

    @override_settings(**RELAY_SETTINGS)
    @patch(SEND_TARGET)
    def test_second_reminder_is_sent_when_first_one_fails(self, send_transient):
        now = self.reminder_run_time()
        course = self.create_course()
        user = self.create_user("student", "student@example.com")
        self.create_enrollment(user, course)
        self.create_two_homeworks(course, now)

        send_transient.side_effect = [
            requests.Timeout("timed out"),
            {"enqueued_count": 1},
        ]

        out = StringIO()
        err = StringIO()
        with self.assertRaises(CommandError):
            self.run_deadline_reminders(now, stdout=out, stderr=err)

        # Both events must have been attempted, not just the first.
        self.assertEqual(send_transient.call_count, 2)

    @override_settings(**RELAY_SETTINGS)
    @patch(SEND_TARGET)
    def test_failure_is_reported_on_stderr_with_reason(self, send_transient):
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

        send_transient.side_effect = requests.Timeout("timed out")

        out = StringIO()
        err = StringIO()
        with self.assertRaises(CommandError):
            self.run_deadline_reminders(now, stdout=out, stderr=err)

        error_output = err.getvalue()
        self.assertIn("homework-1", error_output)
        self.assertIn("timed out", error_output)

    @override_settings(**RELAY_SETTINGS)
    @patch(SEND_TARGET)
    def test_failed_send_records_error_on_audit(self, send_transient):
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

        send_transient.side_effect = requests.Timeout("timed out")

        with self.assertRaises(CommandError):
            self.run_deadline_reminders(now, stdout=StringIO(), stderr=StringIO())

        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.status, DatamailerSendAuditStatus.FAILED)
        self.assertIn("timed out", audit.error)
