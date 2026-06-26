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
        reminders=True,
        preferred_timezone="",
    ):
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password="password",
        )
        user.email_deadline_reminders = reminders
        user.preferred_timezone = preferred_timezone
        user.save(update_fields=["email_deadline_reminders", "preferred_timezone"])
        return user

    def create_enrollment(self, user, course):
        return Enrollment.objects.create(student=user, course=course)

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.DatamailerClient.reconcile_recipient_list_members"
    )
    def test_homework_deadline_reminder_reconciles_eligible_learners(
        self,
        reconcile,
        send_list,
    ):
        now = self.reminder_run_time()
        send_list.return_value = {"enqueued_count": 1}
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
            reminders=False,
        )
        eligible_enrollment = self.create_enrollment(
            eligible_user,
            course,
        )
        submitted_enrollment = self.create_enrollment(
            submitted_user,
            course,
        )
        self.create_enrollment(opted_out_user, course)
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
            "Prepared 1 reminder event(s), 1 member(s).",
            out.getvalue(),
        )
        reconcile.assert_called_once()
        send_list.assert_called_once()
        self.assertEqual(
            reconcile.call_args.args[0],
            "deadline-reminders:homework:ml-zoomcamp-2026:homework-1:24h",
        )
        payload = reconcile.call_args.args[1]
        self.assertEqual(payload["list"]["type"], "deadline_reminders")
        self.assertEqual(len(payload["members"]), 1)
        self.assertEqual(
            payload["members"][0]["email"],
            "eligible@example.com",
        )
        self.assertEqual(
            payload["members"][0]["source_object_key"],
            f"enrollment:{eligible_enrollment.pk}",
        )
        self.assertEqual(
            payload["members"][0]["metadata"]["deadline_at"],
            "Thursday, 18 June 2026, 01:00 Europe/Berlin",
        )
        self.assertEqual(
            payload["members"][0]["metadata"]["deadline_timezone"],
            "Europe/Berlin",
        )

        send_payload = send_list.call_args.args[1]
        self.assertEqual(
            send_payload["template_key"],
            "deadline-reminder",
        )
        self.assertEqual(send_payload["category_tag"], "deadline-reminders")
        self.assertEqual(
            send_payload["idempotency_key"],
            f"deadline-reminder:homework:{homework.pk}:24h",
        )
        self.assertEqual(
            send_payload["context"]["action_url"],
            "https://courses.example.com/ml-zoomcamp-2026/homework/homework-1",
        )
        self.assertEqual(
            send_payload["context"]["deadline_at"],
            "Wednesday, 17 June 2026, 23:00 UTC",
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.DatamailerClient.reconcile_recipient_list_members"
    )
    def test_project_deadline_reminders_use_7d_and_24h_windows(
        self,
        reconcile,
        send_list,
    ):
        now = self.reminder_run_time()
        send_list.return_value = {"enqueued_count": 1}
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        user = self.create_user("student", "student@example.com")
        self.create_enrollment(user, course)
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

        self.assertEqual(reconcile.call_count, 2)
        list_keys = [call.args[0] for call in reconcile.call_args_list]
        self.assertEqual(
            list_keys,
            [
                "deadline-reminders:project-submission:ml-zoomcamp-2026:project-day:24h",
                "deadline-reminders:project-submission:ml-zoomcamp-2026:project-week:7d",
            ],
        )
        send_payloads = [
            call.args[1] for call in send_list.call_args_list
        ]
        self.assertEqual(
            [
                payload["context"]["reminder_key"]
                for payload in send_payloads
            ],
            ["24h", "7d"],
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.DatamailerClient.reconcile_recipient_list_members"
    )
    def test_peer_review_deadline_reminder_targets_unfinished_reviewers(
        self,
        reconcile,
        send_list,
    ):
        now = self.reminder_run_time()
        send_list.return_value = {"enqueued_count": 1}
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        reviewer = self.create_user(
            "reviewer",
            "reviewer@example.com",
        )
        author = self.create_user("author", "author@example.com")
        reviewer_enrollment = self.create_enrollment(reviewer, course)
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
        PeerReview.objects.create(
            submission_under_evaluation=author_submission,
            reviewer=reviewer_submission,
            state=PeerReviewState.TO_REVIEW.value,
        )

        call_command(
            "send_deadline_reminders",
            "--now",
            now.isoformat(),
        )

        reconcile.assert_called_once()
        self.assertEqual(
            reconcile.call_args.args[0],
            "deadline-reminders:peer-review:ml-zoomcamp-2026:project-1:24h",
        )
        payload = reconcile.call_args.args[1]
        self.assertEqual(len(payload["members"]), 1)
        self.assertEqual(
            payload["members"][0]["email"],
            "reviewer@example.com",
        )
        self.assertEqual(
            payload["members"][0]["source_object_key"],
            f"project-submission:{reviewer_submission.pk}",
        )
        send_payload = send_list.call_args.args[1]
        self.assertEqual(
            send_payload["idempotency_key"],
            f"deadline-reminder:peer-review:{project.pk}:24h",
        )
        self.assertEqual(
            send_payload["context"]["action_url"],
            "https://courses.example.com/ml-zoomcamp-2026/project/project-1/eval",
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.DatamailerClient.reconcile_recipient_list_members"
    )
    def test_deadline_reminder_dry_run_does_not_call_datamailer(
        self,
        reconcile,
        send_list,
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
        reconcile.assert_not_called()
        send_list.assert_not_called()
