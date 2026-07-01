from dataclasses import dataclass
from datetime import timedelta

from courses.models import Enrollment, Homework, Submission
from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)


@dataclass(frozen=True)
class HomeworkReminderFixture:
    homework: Homework
    eligible_enrollment: Enrollment
    opted_out_enrollment: Enrollment


@dataclass(frozen=True)
class HomeworkReminderUsers:
    eligible_user: object
    submitted_user: object
    opted_out_user: object


@dataclass(frozen=True)
class HomeworkReminderEnrollments:
    eligible_enrollment: Enrollment
    submitted_enrollment: Enrollment
    opted_out_enrollment: Enrollment


class HomeworkReminderTestMixin:
    def create_homework(self, course, now):
        return Homework.objects.create(
            course=course,
            slug="homework-1",
            title="Homework 1",
            due_date=now + timedelta(days=1, hours=14),
        )

    def create_homework_reminder_users(self):
        eligible_user = self.create_user(
            "eligible",
            "eligible@example.com",
            preferred_timezone="Europe/Berlin",
        )
        submitted_user = self.create_user(
            "submitted",
            "submitted@example.com",
        )
        opted_out_user = self.create_user(
            "opted-out",
            "opted-out@example.com",
        )
        return HomeworkReminderUsers(
            eligible_user=eligible_user,
            submitted_user=submitted_user,
            opted_out_user=opted_out_user,
        )

    def create_homework_reminder_enrollments(self, course, users):
        eligible_enrollment = self.create_enrollment(
            users.eligible_user,
            course,
        )
        submitted_enrollment = self.create_enrollment(
            users.submitted_user,
            course,
        )
        opted_out_enrollment = self.create_enrollment(
            users.opted_out_user,
            course,
        )
        return HomeworkReminderEnrollments(
            eligible_enrollment=eligible_enrollment,
            submitted_enrollment=submitted_enrollment,
            opted_out_enrollment=opted_out_enrollment,
        )

    def create_submitted_homework(self, homework, user, enrollment):
        Submission.objects.create(
            homework=homework,
            student=user,
            enrollment=enrollment,
        )

    def create_homework_reminder_fixture(self, now):
        course = self.create_course()
        homework = self.create_homework(course, now)
        users = self.create_homework_reminder_users()
        enrollments = self.create_homework_reminder_enrollments(
            course,
            users,
        )
        self.create_submitted_homework(
            homework,
            users.submitted_user,
            enrollments.submitted_enrollment,
        )
        return HomeworkReminderFixture(
            homework=homework,
            eligible_enrollment=enrollments.eligible_enrollment,
            opted_out_enrollment=enrollments.opted_out_enrollment,
        )

    def assert_homework_reminder_list(self, payload):
        self.assertEqual(
            payload["list"]["key"],
            "deadline-reminders:homework:ml-zoomcamp-2026:homework-1:24h",
        )
        self.assertEqual(
            payload["list"]["name"],
            "ML Zoomcamp 2026 Homework 1 24h deadline reminders",
        )
        self.assertEqual(
            payload["list"]["metadata"]["deadline_kind"],
            "homework",
        )

    def assert_homework_reminder_members(
        self,
        members_by_email,
        expectation,
    ):
        expected_emails = {"eligible@example.com", "opted-out@example.com"}
        self.assertEqual(set(members_by_email), expected_emails)
        eligible_member = members_by_email["eligible@example.com"]
        opted_out_member = members_by_email["opted-out@example.com"]
        self.assertEqual(
            eligible_member["source_object_key"],
            f"enrollment:{expectation.eligible_enrollment.pk}",
        )
        self.assertEqual(
            opted_out_member["source_object_key"],
            f"enrollment:{expectation.opted_out_enrollment.pk}",
        )

    def assert_homework_reminder_idempotency(self, payload, expectation):
        self.assertEqual(
            payload["idempotency_key"],
            f"deadline-reminder:homework:{expectation.homework.pk}:24h",
        )

    def assert_homework_reminder_payload(self, payload, expectation):
        self.assert_homework_reminder_list(payload)
        members_by_email = self.members_by_email(payload)
        self.assert_homework_reminder_members(members_by_email, expectation)
        self.assert_homework_reminder_context(payload, members_by_email)
        self.assert_homework_reminder_idempotency(payload, expectation)

    def assert_homework_reminder_context(self, payload, members_by_email):
        self.assertEqual(
            members_by_email["eligible@example.com"]["metadata"]["deadline_at"],
            "Thursday, 18 June 2026, 01:00 Europe/Berlin",
        )
        self.assertEqual(
            members_by_email["eligible@example.com"]["metadata"][
                "deadline_timezone"
            ],
            "Europe/Berlin",
        )
        self.assertEqual(payload["template_key"], "deadline-reminder")
        self.assertEqual(payload["category_tag"], "deadline-reminders")
        self.assertEqual(
            payload["context"]["action_url"],
            "https://courses.example.com/ml-zoomcamp-2026/homework/homework-1",
        )
        self.assertEqual(
            payload["context"]["deadline_at"],
            "Wednesday, 17 June 2026, 23:00 UTC",
        )

    def assert_homework_reminder_audit(self, homework):
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(
            audit.send_type,
            DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
        )
        self.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
        self.assertEqual(
            audit.idempotency_key,
            f"deadline-reminder:homework:{homework.pk}:24h",
        )
        self.assertEqual(audit.template_key, "deadline-reminder")
        self.assertEqual(audit.category_tag, "deadline-reminders")
        self.assertEqual(audit.event, "deadline_reminder")
        self.assertEqual(
            audit.list_key,
            "deadline-reminders:homework:ml-zoomcamp-2026:homework-1:24h",
        )
        self.assertEqual(audit.intended_count, 2)
        self.assertEqual(audit.enqueued_count, 1)
