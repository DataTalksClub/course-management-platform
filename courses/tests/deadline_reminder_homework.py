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


def create_homework(course, now):
    return Homework.objects.create(
        course=course,
        slug="homework-1",
        title="Homework 1",
        due_date=now + timedelta(days=1, hours=14),
    )


def create_homework_reminder_users(test_case):
    eligible_user = test_case.create_user(
        "eligible",
        "eligible@example.com",
        preferred_timezone="Europe/Berlin",
    )
    submitted_user = test_case.create_user(
        "submitted",
        "submitted@example.com",
    )
    opted_out_user = test_case.create_user(
        "opted-out",
        "opted-out@example.com",
    )
    return HomeworkReminderUsers(
        eligible_user=eligible_user,
        submitted_user=submitted_user,
        opted_out_user=opted_out_user,
    )


def create_homework_reminder_enrollments(test_case, course, users):
    eligible_enrollment = test_case.create_enrollment(
        users.eligible_user,
        course,
    )
    submitted_enrollment = test_case.create_enrollment(
        users.submitted_user,
        course,
    )
    opted_out_enrollment = test_case.create_enrollment(
        users.opted_out_user,
        course,
    )
    return HomeworkReminderEnrollments(
        eligible_enrollment=eligible_enrollment,
        submitted_enrollment=submitted_enrollment,
        opted_out_enrollment=opted_out_enrollment,
    )


def create_submitted_homework(homework, user, enrollment):
    Submission.objects.create(
        homework=homework,
        student=user,
        enrollment=enrollment,
    )


def create_homework_reminder_fixture(test_case, now):
    course = test_case.create_course()
    homework = create_homework(course, now)
    users = create_homework_reminder_users(test_case)
    enrollments = create_homework_reminder_enrollments(
        test_case,
        course,
        users,
    )
    create_submitted_homework(
        homework,
        users.submitted_user,
        enrollments.submitted_enrollment,
    )
    return HomeworkReminderFixture(
        homework=homework,
        eligible_enrollment=enrollments.eligible_enrollment,
        opted_out_enrollment=enrollments.opted_out_enrollment,
    )


def assert_homework_reminder_list(test_case, payload):
    test_case.assertEqual(
        payload["list"]["key"],
        "deadline-reminders:homework:ml-zoomcamp-2026:homework-1:24h",
    )
    test_case.assertEqual(
        payload["list"]["name"],
        "ML Zoomcamp 2026 Homework 1 24h deadline reminders",
    )
    test_case.assertEqual(
        payload["list"]["metadata"]["deadline_kind"],
        "homework",
    )


def assert_homework_reminder_members(
    test_case,
    members_by_email,
    expectation,
):
    expected_emails = {"eligible@example.com", "opted-out@example.com"}
    test_case.assertEqual(set(members_by_email), expected_emails)
    eligible_member = members_by_email["eligible@example.com"]
    opted_out_member = members_by_email["opted-out@example.com"]
    test_case.assertEqual(
        eligible_member["source_object_key"],
        f"enrollment:{expectation.eligible_enrollment.pk}",
    )
    test_case.assertEqual(
        opted_out_member["source_object_key"],
        f"enrollment:{expectation.opted_out_enrollment.pk}",
    )


def assert_homework_reminder_idempotency(test_case, payload, expectation):
    test_case.assertEqual(
        payload["idempotency_key"],
        f"deadline-reminder:homework:{expectation.homework.pk}:24h",
    )


def assert_homework_reminder_payload(test_case, payload, expectation):
    assert_homework_reminder_list(test_case, payload)
    members_by_email = test_case.members_by_email(payload)
    assert_homework_reminder_members(
        test_case,
        members_by_email,
        expectation,
    )
    assert_homework_reminder_context(test_case, payload, members_by_email)
    assert_homework_reminder_idempotency(test_case, payload, expectation)


def assert_homework_reminder_context(test_case, payload, members_by_email):
    test_case.assertEqual(
        members_by_email["eligible@example.com"]["metadata"]["deadline_at"],
        "Thursday, 18 June 2026, 01:00 Europe/Berlin",
    )
    test_case.assertEqual(
        members_by_email["eligible@example.com"]["metadata"][
            "deadline_timezone"
        ],
        "Europe/Berlin",
    )
    test_case.assertEqual(payload["template_key"], "deadline-reminder")
    test_case.assertEqual(payload["category_tag"], "deadline-reminders")
    test_case.assertEqual(
        payload["context"]["action_url"],
        "https://courses.example.com/ml-zoomcamp-2026/homework/homework-1",
    )
    test_case.assertEqual(
        payload["context"]["deadline_at"],
        "Wednesday, 17 June 2026, 23:00 UTC",
    )


def assert_homework_reminder_audit(test_case, homework):
    audit = DatamailerSendAudit.objects.get()
    test_case.assertEqual(
        audit.send_type,
        DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
    )
    test_case.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
    test_case.assertEqual(
        audit.idempotency_key,
        f"deadline-reminder:homework:{homework.pk}:24h",
    )
    test_case.assertEqual(audit.template_key, "deadline-reminder")
    test_case.assertEqual(audit.category_tag, "deadline-reminders")
    test_case.assertEqual(audit.event, "deadline_reminder")
    test_case.assertEqual(
        audit.list_key,
        "deadline-reminders:homework:ml-zoomcamp-2026:homework-1:24h",
    )
    test_case.assertEqual(audit.intended_count, 2)
    test_case.assertEqual(audit.enqueued_count, 1)
