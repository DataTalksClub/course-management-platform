from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as datetime_timezone
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import CustomUser
from courses.models import (
    Course,
    Enrollment,
    Homework,
    PeerReview,
    PeerReviewState,
    Project,
    ProjectState,
    ProjectSubmission,
    Submission,
)
from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


@dataclass(frozen=True)
class ProjectReminderData:
    course: Course
    now: datetime
    slug: str
    title: str
    submission_delta: timedelta
    state: str


@dataclass(frozen=True)
class ProjectSubmissionData:
    project: Project
    user: CustomUser
    enrollment: Enrollment
    label: str


@dataclass(frozen=True)
class HomeworkReminderFixture:
    homework: Homework
    eligible_enrollment: Enrollment
    opted_out_enrollment: Enrollment


@dataclass(frozen=True)
class PeerReviewReminderFixture:
    project: Project
    reviewer_submission: ProjectSubmission
    opted_out_submission: ProjectSubmission


class DeadlineReminderCommandTest(TestCase):
    def reminder_run_time(self):
        return datetime(2026, 6, 16, 9, tzinfo=datetime_timezone.utc)

    def create_user(
        self,
        username,
        email,
        *,
        preferred_timezone="",
    ):
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password="password",
        )
        user.preferred_timezone = preferred_timezone
        user.save(update_fields=["preferred_timezone"])
        return user

    def create_enrollment(self, user, course):
        return Enrollment.objects.create(student=user, course=course)

    def create_course(self):
        return Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )

    def create_homework(self, course, now):
        return Homework.objects.create(
            course=course,
            slug="homework-1",
            title="Homework 1",
            due_date=now + timedelta(days=1, hours=14),
        )

    def create_project(self, data):
        return Project.objects.create(
            course=data.course,
            slug=data.slug,
            title=data.title,
            submission_due_date=data.now + data.submission_delta,
            peer_review_due_date=data.now + timedelta(days=10),
            state=data.state,
        )

    def create_project_submission(self, data):
        return ProjectSubmission.objects.create(
            project=data.project,
            student=data.user,
            enrollment=data.enrollment,
            github_link=f"https://github.com/{data.label}/project",
            commit_id="1234567",
        )

    def run_deadline_reminders(self, now, stdout=None, dry_run=False):
        args = ["send_deadline_reminders", "--now", now.isoformat()]
        if dry_run:
            args.append("--dry-run")
        call_command(*args, stdout=stdout)

    def members_by_email(self, payload):
        members_by_email = {}
        members = payload["members"]
        for member in members:
            email = member["email"]
            members_by_email[email] = member
        return members_by_email

    def create_homework_reminder_fixture(self, now):
        course = self.create_course()
        homework = self.create_homework(course, now)
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
        eligible_enrollment = self.create_enrollment(eligible_user, course)
        submitted_enrollment = self.create_enrollment(
            submitted_user, course
        )
        opted_out_enrollment = self.create_enrollment(
            opted_out_user, course
        )
        Submission.objects.create(
            homework=homework,
            student=submitted_user,
            enrollment=submitted_enrollment,
        )
        return HomeworkReminderFixture(
            homework=homework,
            eligible_enrollment=eligible_enrollment,
            opted_out_enrollment=opted_out_enrollment,
        )

    def assert_homework_reminder_payload(self, payload, expectation):
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
        members_by_email = self.members_by_email(payload)
        self.assertEqual(
            set(members_by_email),
            {"eligible@example.com", "opted-out@example.com"},
        )
        self.assertEqual(
            members_by_email["eligible@example.com"]["source_object_key"],
            f"enrollment:{expectation.eligible_enrollment.pk}",
        )
        self.assertEqual(
            members_by_email["opted-out@example.com"]["source_object_key"],
            f"enrollment:{expectation.opted_out_enrollment.pk}",
        )
        self.assert_homework_reminder_context(payload, members_by_email)
        self.assertEqual(
            payload["idempotency_key"],
            f"deadline-reminder:homework:{expectation.homework.pk}:24h",
        )

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

    def create_project_submission_reminder_fixture(self, now):
        course = self.create_course()
        user = self.create_user("student", "student@example.com")
        opted_out_user = self.create_user(
            "opted-out",
            "opted-out@example.com",
        )
        self.create_enrollment(user, course)
        self.create_enrollment(opted_out_user, course)
        project_week = ProjectReminderData(
            course=course,
            now=now,
            slug="project-week",
            title="Project Week",
            submission_delta=timedelta(days=8, hours=2),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )
        self.create_project(project_week)
        project_day = ProjectReminderData(
            course=course,
            now=now,
            slug="project-day",
            title="Project Day",
            submission_delta=timedelta(days=1, hours=14),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )
        self.create_project(project_day)

    def assert_project_reminder_payloads(self, send_transient):
        self.assertEqual(send_transient.call_count, 2)
        send_payloads = []
        send_calls = send_transient.call_args_list
        for call in send_calls:
            payload = call.args[0]
            send_payloads.append(payload)
        list_keys = []
        for payload in send_payloads:
            list_key = payload["list"]["key"]
            list_keys.append(list_key)
        self.assertEqual(
            list_keys,
            [
                "deadline-reminders:project-submission:"
                "ml-zoomcamp-2026:project-day:24h",
                "deadline-reminders:project-submission:"
                "ml-zoomcamp-2026:project-week:7d",
            ],
        )
        reminder_keys = []
        for payload in send_payloads:
            reminder_key = payload["context"]["reminder_key"]
            reminder_keys.append(reminder_key)
        self.assertEqual(
            reminder_keys,
            ["24h", "7d"],
        )
        for payload in send_payloads:
            member_emails = set()
            members = payload["members"]
            for member in members:
                email = member["email"]
                member_emails.add(email)
            self.assertEqual(
                member_emails,
                {"student@example.com", "opted-out@example.com"},
            )

    def create_peer_review_reminder_fixture(self, now):
        course = self.create_course()
        reviewer = self.create_user("reviewer", "reviewer@example.com")
        opted_out_reviewer = self.create_user(
            "opted-out-reviewer",
            "opted-out-reviewer@example.com",
        )
        author = self.create_user("author", "author@example.com")
        reviewer_enrollment = self.create_enrollment(reviewer, course)
        opted_out_enrollment = self.create_enrollment(
            opted_out_reviewer,
            course,
        )
        author_enrollment = self.create_enrollment(author, course)
        project = Project.objects.create(
            course=course,
            slug="project-1",
            title="Project 1",
            submission_due_date=now - timedelta(days=1),
            peer_review_due_date=now + timedelta(days=1, hours=14),
            state=ProjectState.PEER_REVIEWING.value,
        )
        reviewer_submission_data = ProjectSubmissionData(
            project=project,
            user=reviewer,
            enrollment=reviewer_enrollment,
            label="reviewer",
        )
        reviewer_submission = self.create_project_submission(
            reviewer_submission_data
        )
        author_submission_data = ProjectSubmissionData(
            project=project,
            user=author,
            enrollment=author_enrollment,
            label="author",
        )
        author_submission = self.create_project_submission(
            author_submission_data
        )
        opted_out_submission_data = ProjectSubmissionData(
            project=project,
            user=opted_out_reviewer,
            enrollment=opted_out_enrollment,
            label="opted-out",
        )
        opted_out_submission = self.create_project_submission(
            opted_out_submission_data
        )
        self.create_pending_peer_review(author_submission, reviewer_submission)
        self.create_pending_peer_review(author_submission, opted_out_submission)
        return PeerReviewReminderFixture(
            project=project,
            reviewer_submission=reviewer_submission,
            opted_out_submission=opted_out_submission,
        )

    def create_pending_peer_review(self, author_submission, reviewer):
        return PeerReview.objects.create(
            submission_under_evaluation=author_submission,
            reviewer=reviewer,
            state=PeerReviewState.TO_REVIEW.value,
        )

    def assert_peer_review_reminder_payload(self, payload, expectation):
        self.assertEqual(
            payload["list"]["key"],
            "deadline-reminders:peer-review:ml-zoomcamp-2026:project-1:24h",
        )
        members_by_email = self.members_by_email(payload)
        self.assertEqual(
            set(members_by_email),
            {
                "reviewer@example.com",
                "opted-out-reviewer@example.com",
            },
        )
        self.assertEqual(
            members_by_email["reviewer@example.com"]["source_object_key"],
            f"project-submission:{expectation.reviewer_submission.pk}",
        )
        self.assertEqual(
            members_by_email["opted-out-reviewer@example.com"][
                "source_object_key"
            ],
            f"project-submission:{expectation.opted_out_submission.pk}",
        )
        self.assertEqual(
            payload["idempotency_key"],
            f"deadline-reminder:peer-review:{expectation.project.pk}:24h",
        )
        self.assertEqual(
            payload["context"]["action_url"],
            "https://courses.example.com/ml-zoomcamp-2026/project/project-1/eval",
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transient_recipient_list_transactional"
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

        self.assertIn(
            "Prepared 1 reminder event(s), 2 member(s).",
            out.getvalue(),
        )
        send_transient.assert_called_once()
        payload = send_transient.call_args.args[0]
        self.assert_homework_reminder_payload(
            payload,
            fixture,
        )
        self.assert_homework_reminder_audit(fixture.homework)

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transient_recipient_list_transactional"
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

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transient_recipient_list_transactional"
    )
    def test_peer_review_deadline_reminder_targets_unfinished_reviewers(
        self,
        send_transient,
    ):
        now = self.reminder_run_time()
        send_transient.return_value = {"enqueued_count": 1}
        fixture = self.create_peer_review_reminder_fixture(now)

        self.run_deadline_reminders(now)

        send_transient.assert_called_once()
        payload = send_transient.call_args.args[0]
        self.assert_peer_review_reminder_payload(
            payload,
            fixture,
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transient_recipient_list_transactional"
    )
    def test_deadline_reminder_dry_run_does_not_call_datamailer(
        self,
        send_transient,
    ):
        now = self.reminder_run_time()
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        user = self.create_user("student", "student@example.com")
        self.create_enrollment(user, course)
        Homework.objects.create(
            course=course,
            slug="homework-1",
            title="Homework 1",
            due_date=now + timedelta(days=1, hours=14),
        )

        out = StringIO()
        call_command(
            "send_deadline_reminders",
            "--now",
            now.isoformat(),
            "--dry-run",
            stdout=out,
        )

        self.assertIn(
            "deadline-reminders:homework:ml-zoomcamp-2026:homework-1:24h: 1 member(s)",
            out.getvalue(),
        )
        send_transient.assert_not_called()
