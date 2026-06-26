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

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.DatamailerClient.send_transient_recipient_list_transactional"
    )
    def test_homework_deadline_reminder_sends_transient_eligible_learners(
        self,
        send_transient,
    ):
        now = self.reminder_run_time()
        send_transient.return_value = {"enqueued_count": 1}
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        homework = Homework.objects.create(
            course=course,
            slug="homework-1",
            title="Homework 1",
            due_date=now + timedelta(days=1, hours=14),
        )
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
        eligible_enrollment = self.create_enrollment(
            eligible_user,
            course,
        )
        submitted_enrollment = self.create_enrollment(
            submitted_user,
            course,
        )
        opted_out_enrollment = self.create_enrollment(opted_out_user, course)
        Submission.objects.create(
            homework=homework,
            student=submitted_user,
            enrollment=submitted_enrollment,
        )

        out = StringIO()
        call_command(
            "send_deadline_reminders",
            "--now",
            now.isoformat(),
            stdout=out,
        )

        self.assertIn(
            "Prepared 1 reminder event(s), 2 member(s).",
            out.getvalue(),
        )
        send_transient.assert_called_once()
        payload = send_transient.call_args.args[0]
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
        members_by_email = {m["email"]: m for m in payload["members"]}
        self.assertEqual(
            set(members_by_email),
            {"eligible@example.com", "opted-out@example.com"},
        )
        self.assertEqual(
            members_by_email["eligible@example.com"]["source_object_key"],
            f"enrollment:{eligible_enrollment.pk}",
        )
        self.assertEqual(
            members_by_email["opted-out@example.com"]["source_object_key"],
            f"enrollment:{opted_out_enrollment.pk}",
        )
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
        self.assertEqual(
            payload["template_key"],
            "deadline-reminder",
        )
        self.assertEqual(payload["category_tag"], "deadline-reminders")
        self.assertEqual(
            payload["idempotency_key"],
            f"deadline-reminder:homework:{homework.pk}:24h",
        )
        self.assertEqual(
            payload["context"]["action_url"],
            "https://courses.example.com/ml-zoomcamp-2026/homework/homework-1",
        )
        self.assertEqual(
            payload["context"]["deadline_at"],
            "Wednesday, 17 June 2026, 23:00 UTC",
        )
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

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.DatamailerClient.send_transient_recipient_list_transactional"
    )
    def test_project_deadline_reminders_use_7d_and_24h_windows(
        self,
        send_transient,
    ):
        now = self.reminder_run_time()
        send_transient.return_value = {"enqueued_count": 1}
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        user = self.create_user("student", "student@example.com")
        opted_out_user = self.create_user(
            "opted-out",
            "opted-out@example.com",
        )
        self.create_enrollment(user, course)
        self.create_enrollment(opted_out_user, course)
        Project.objects.create(
            course=course,
            slug="project-week",
            title="Project Week",
            submission_due_date=now + timedelta(days=8, hours=2),
            peer_review_due_date=now + timedelta(days=10),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )
        Project.objects.create(
            course=course,
            slug="project-day",
            title="Project Day",
            submission_due_date=now + timedelta(days=1, hours=14),
            peer_review_due_date=now + timedelta(days=10),
            state=ProjectState.COLLECTING_SUBMISSIONS.value,
        )

        call_command(
            "send_deadline_reminders",
            "--now",
            now.isoformat(),
        )

        self.assertEqual(send_transient.call_count, 2)
        list_keys = [
            call.args[0]["list"]["key"]
            for call in send_transient.call_args_list
        ]
        self.assertEqual(
            list_keys,
            [
                "deadline-reminders:project-submission:ml-zoomcamp-2026:project-day:24h",
                "deadline-reminders:project-submission:ml-zoomcamp-2026:project-week:7d",
            ],
        )
        send_payloads = [
            call.args[0] for call in send_transient.call_args_list
        ]
        self.assertEqual(
            [
                payload["context"]["reminder_key"]
                for payload in send_payloads
            ],
            ["24h", "7d"],
        )
        for payload in send_payloads:
            self.assertEqual(
                {member["email"] for member in payload["members"]},
                {"student@example.com", "opted-out@example.com"},
            )

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.DatamailerClient.send_transient_recipient_list_transactional"
    )
    def test_peer_review_deadline_reminder_targets_unfinished_reviewers(
        self,
        send_transient,
    ):
        now = self.reminder_run_time()
        send_transient.return_value = {"enqueued_count": 1}
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        reviewer = self.create_user(
            "reviewer",
            "reviewer@example.com",
        )
        opted_out_reviewer = self.create_user(
            "opted-out-reviewer",
            "opted-out-reviewer@example.com",
        )
        author = self.create_user("author", "author@example.com")
        reviewer_enrollment = self.create_enrollment(reviewer, course)
        opted_out_reviewer_enrollment = self.create_enrollment(
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
        reviewer_submission = ProjectSubmission.objects.create(
            project=project,
            student=reviewer,
            enrollment=reviewer_enrollment,
            github_link="https://github.com/reviewer/project",
            commit_id="1234567",
        )
        author_submission = ProjectSubmission.objects.create(
            project=project,
            student=author,
            enrollment=author_enrollment,
            github_link="https://github.com/author/project",
            commit_id="1234567",
        )
        opted_out_reviewer_submission = ProjectSubmission.objects.create(
            project=project,
            student=opted_out_reviewer,
            enrollment=opted_out_reviewer_enrollment,
            github_link="https://github.com/opted-out/project",
            commit_id="1234567",
        )
        PeerReview.objects.create(
            submission_under_evaluation=author_submission,
            reviewer=reviewer_submission,
            state=PeerReviewState.TO_REVIEW.value,
        )
        PeerReview.objects.create(
            submission_under_evaluation=author_submission,
            reviewer=opted_out_reviewer_submission,
            state=PeerReviewState.TO_REVIEW.value,
        )

        call_command(
            "send_deadline_reminders",
            "--now",
            now.isoformat(),
        )

        send_transient.assert_called_once()
        payload = send_transient.call_args.args[0]
        self.assertEqual(
            payload["list"]["key"],
            "deadline-reminders:peer-review:ml-zoomcamp-2026:project-1:24h",
        )
        members_by_email = {m["email"]: m for m in payload["members"]}
        self.assertEqual(
            set(members_by_email),
            {
                "reviewer@example.com",
                "opted-out-reviewer@example.com",
            },
        )
        self.assertEqual(
            members_by_email["reviewer@example.com"]["source_object_key"],
            f"project-submission:{reviewer_submission.pk}",
        )
        self.assertEqual(
            members_by_email["opted-out-reviewer@example.com"][
                "source_object_key"
            ],
            f"project-submission:{opted_out_reviewer_submission.pk}",
        )
        self.assertEqual(
            payload["idempotency_key"],
            f"deadline-reminder:peer-review:{project.pk}:24h",
        )
        self.assertEqual(
            payload["context"]["action_url"],
            "https://courses.example.com/ml-zoomcamp-2026/project/project-1/eval",
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.send_transient_recipient_list_transactional"
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
