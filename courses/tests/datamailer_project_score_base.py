from dataclasses import dataclass
from datetime import timedelta
from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
)
from course_management.datamailer.keys import (
    project_passed_list_key,
    project_submitters_list_key,
)
from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectSubmission,
)


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


@dataclass(frozen=True)
class ScorePayloadExpectation:
    payload: dict
    template_key: str
    idempotency_key: str
    footer_text: str
    list_type: str


@dataclass(frozen=True)
class ProjectScoreListSendExpectation:
    result: dict
    bulk_upsert: Mock
    send_list: Mock
    project: Project
    submission: ProjectSubmission


class DatamailerProjectScoreTestBase(TestCase):
    def create_ml_course(self):
        return Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )

    def create_project(self, course=None, **overrides):
        defaults = {
            "course": course or self.create_ml_course(),
            "slug": "project-1",
            "title": "Project 1",
            "submission_due_date": "2026-01-01T00:00:00Z",
            "peer_review_due_date": "2026-01-08T00:00:00Z",
        }
        defaults.update(overrides)
        return Project.objects.create(**defaults)

    def create_user(self, email):
        return CustomUser.objects.create_user(
            username=email,
            email=email,
            password="test",
        )

    def create_enrollment(self, user, course, **overrides):
        defaults = {"student": user, "course": course}
        defaults.update(overrides)
        return Enrollment.objects.create(**defaults)

    def create_project_submission(self, project, user, **overrides):
        enrollment = self.create_enrollment(user, project.course)
        defaults = {
            "project": project,
            "student": user,
            "enrollment": enrollment,
            "github_link": "https://github.com/example/project",
            "commit_id": "abc123",
        }
        defaults.update(overrides)
        return ProjectSubmission.objects.create(**defaults)

    def assert_score_payload_common(self, expectation):
        payload = expectation.payload
        self.assertEqual(payload["template_key"], expectation.template_key)
        self.assertEqual(
            payload["idempotency_key"],
            expectation.idempotency_key,
        )
        self.assertEqual(payload["from_email"], "courses")
        self.assertEqual(
            payload["context"]["profile_url"],
            "https://courses.example.com/accounts/settings/",
        )
        self.assertIn(
            expectation.footer_text,
            payload["context"]["notification_footer"],
        )
        self.assertEqual(
            payload["metadata"]["preference_key"],
            "email_submission_confirmations",
        )
        self.assertEqual(payload["category_tag"], "submission-results")
        self.assertNotIn("member_sync", payload)
        self.assertNotIn("remove_absent_members", payload)
        self.assertEqual(payload["list"]["type"], expectation.list_type)
        member_count = len(payload["members"])
        self.assertEqual(member_count, 1)
        return payload["members"][0]

    def single_project_score_member(self, payload):
        member_count = len(payload["members"])
        self.assertEqual(member_count, 1)
        return payload["members"][0]

    def assert_project_score_member(self, member, submission):
        self.assertEqual(
            member["source_object_key"],
            f"project-submission:{submission.pk}",
        )
        self.assertEqual(member["email"], "project-learner@example.com")
        self.assertEqual(member["metadata"]["project_score"], 70)
        self.assertEqual(
            member["metadata"]["project_learning_in_public_score"],
            5,
        )
        self.assertEqual(member["metadata"]["project_faq_score"], 1)
        self.assertEqual(member["metadata"]["peer_review_score"], 18)
        self.assertEqual(
            member["metadata"]["peer_review_learning_in_public_score"],
            4,
        )
        self.assertEqual(member["metadata"]["total_score"], 98)
        self.assertEqual(
            member["metadata"]["github_link"],
            "https://github.com/example/project",
        )
        self.assertEqual(member["metadata"]["commit_id"], "abc123")
        self.assertEqual(
            member["metadata"]["project_url"],
            "https://courses.example.com/ml-zoomcamp-2026/project/project-1",
        )
        self.assertTrue(member["metadata"]["reviewed_enough_peers"])
        self.assertTrue(member["metadata"]["passed"])

    def assert_project_score_context(self, payload):
        self.assertEqual(
            payload["context"]["scores_url"],
            "https://courses.example.com/ml-zoomcamp-2026/project/project-1/results",
        )
        self.assertEqual(
            payload["context"]["project_url"],
            "https://courses.example.com/ml-zoomcamp-2026/project/project-1",
        )
        self.assertEqual(
            payload["context"]["leaderboard_url"],
            "https://courses.example.com/ml-zoomcamp-2026/leaderboard",
        )

    def assert_latest_project_score_member(self, member, submission):
        self.assertEqual(
            member["source_object_key"],
            f"project-submission:{submission.pk}",
        )
        self.assertEqual(member["metadata"]["total_score"], 90)

    def create_passed_and_failed_project_submissions(self):
        project = self.create_project()
        passed_user = self.create_user("passed@example.com")
        passed_submission = self.create_project_submission(
            project,
            passed_user,
            github_link="https://github.com/example/passed",
            total_score=98,
            passed=True,
        )
        failed_user = self.create_user("failed@example.com")
        self.create_project_submission(
            project,
            failed_user,
            github_link="https://github.com/example/failed",
            total_score=50,
            passed=False,
        )
        return project, passed_submission

    def create_duplicate_project_submissions(self):
        project = self.create_project()
        user = self.create_user("project-learner@example.com")
        enrollment = self.create_enrollment(user, project.course)
        older_submission_time = timezone.now() - timedelta(days=1)
        ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/example/old",
            submitted_at=older_submission_time,
            total_score=40,
        )
        latest_submission_time = timezone.now()
        latest_submission = ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/example/new",
            submitted_at=latest_submission_time,
            total_score=90,
        )
        return project, latest_submission

    def create_project_score_submission(self):
        project = self.create_project()
        user = self.create_user("project-learner@example.com")
        submission = self.create_project_submission(
            project,
            user,
            project_score=70,
            project_learning_in_public_score=5,
            project_faq_score=1,
            peer_review_score=18,
            peer_review_learning_in_public_score=4,
            total_score=98,
            reviewed_enough_peers=True,
            passed=True,
        )
        return project, submission

    def assert_project_score_list_send(self, expectation):
        self.assertEqual(expectation.result, {"enqueued_count": 1})
        self.assertEqual(expectation.bulk_upsert.call_count, 2)
        expectation.send_list.assert_called_once()
        outbox_event_count = DatamailerOutboxEvent.objects.filter(
            event_type="recipient_list.members_bulk_upsert",
            status=DatamailerOutboxStatus.ACKED,
        ).count()
        self.assertEqual(outbox_event_count, 2)
        project_submitters_key = project_submitters_list_key(
            expectation.project
        )
        self.assertEqual(
            expectation.send_list.call_args.args[0],
            project_submitters_key,
        )
        self.assertNotIn("members", expectation.send_list.call_args.args[1])
        self.assertNotIn("list", expectation.send_list.call_args.args[1])
        project_passed_key = project_passed_list_key(expectation.project)
        self.assertEqual(
            expectation.bulk_upsert.call_args_list[1].args[0],
            project_passed_key,
        )
        passed_payload = expectation.bulk_upsert.call_args_list[1].args[1]
        self.assertEqual(
            passed_payload["members"][0]["source_object_key"],
            f"project-submission:{expectation.submission.pk}",
        )
        self.assertEqual(
            passed_payload["members"][0]["metadata"]["outcome"],
            "project_passed",
        )
