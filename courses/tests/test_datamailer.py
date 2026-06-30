from dataclasses import dataclass
from datetime import timedelta
from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)
from course_management.datamailer.keys import (
    homework_submitters_list_key,
    project_passed_list_key,
    project_submitters_list_key,
)
from course_management.datamailer.payloads import (
    homework_score_notification_payload,
    project_passed_recipient_list_payload,
    project_score_notification_payload,
)
from course_management.datamailer.sync import (
    send_homework_score_notification,
    send_project_score_notification,
)
from courses.models import (
    Course,
    Enrollment,
    Homework,
    Project,
    ProjectSubmission,
    Submission,
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


@dataclass(frozen=True)
class HomeworkScoreListSendExpectation:
    result: dict
    bulk_upsert: Mock
    send_list: Mock
    homework: Homework


class DatamailerWorkflowTest(TestCase):
    def create_ml_course(self):
        return Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )

    def create_homework(self, course=None):
        return Homework.objects.create(
            course=course or self.create_ml_course(),
            slug="homework-1",
            title="Homework 1",
            due_date="2026-01-01T00:00:00Z",
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

    def create_homework_submission(self, homework, user, **overrides):
        enrollment = overrides.pop("enrollment", None)
        if enrollment is None:
            enrollment = self.create_enrollment(user, homework.course)
        defaults = {
            "homework": homework,
            "student": user,
            "enrollment": enrollment,
        }
        defaults.update(overrides)
        return Submission.objects.create(**defaults)

    def create_project_submission(self, project, user, **overrides):
        defaults = {
            "project": project,
            "student": user,
            "enrollment": self.create_enrollment(user, project.course),
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
        self.assertEqual(len(payload["members"]), 1)
        return payload["members"][0]

    def create_passed_and_failed_project_submissions(self):
        project = self.create_project()
        passed_submission = self.create_project_submission(
            project,
            self.create_user("passed@example.com"),
            github_link="https://github.com/example/passed",
            total_score=98,
            passed=True,
        )
        self.create_project_submission(
            project,
            self.create_user("failed@example.com"),
            github_link="https://github.com/example/failed",
            total_score=50,
            passed=False,
        )
        return project, passed_submission

    def assert_homework_score_member(self, member, submission):
        self.assertEqual(
            member["source_object_key"],
            f"homework-submission:{submission.pk}",
        )
        self.assertEqual(member["email"], "learner@example.com")
        self.assertEqual(member["metadata"]["questions_score"], 6)
        self.assertEqual(
            member["metadata"]["learning_in_public_score"], 2
        )
        self.assertEqual(member["metadata"]["faq_score"], 1)
        self.assertEqual(member["metadata"]["total_score"], 9)
        self.assertEqual(
            member["metadata"]["homework_url"],
            "https://courses.example.com/ml-zoomcamp-2026/homework/homework-1",
        )

    def single_homework_score_member(self, payload):
        self.assertEqual(len(payload["members"]), 1)
        return payload["members"][0]

    def single_project_score_member(self, payload):
        self.assertEqual(len(payload["members"]), 1)
        return payload["members"][0]

    def create_duplicate_homework_submissions(self):
        homework = self.create_homework()
        user = self.create_user("learner@example.com")
        enrollment = self.create_enrollment(user, homework.course)
        self.create_homework_submission(
            homework,
            user,
            enrollment=enrollment,
            submitted_at=timezone.now() - timedelta(days=1),
            total_score=4,
        )
        latest_submission = self.create_homework_submission(
            homework,
            user,
            enrollment=enrollment,
            submitted_at=timezone.now(),
            total_score=9,
        )
        return homework, latest_submission

    def create_duplicate_project_submissions(self):
        project = self.create_project()
        user = self.create_user("project-learner@example.com")
        enrollment = self.create_enrollment(user, project.course)
        ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/example/old",
            submitted_at=timezone.now() - timedelta(days=1),
            total_score=40,
        )
        latest_submission = ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/example/new",
            submitted_at=timezone.now(),
            total_score=90,
        )
        return project, latest_submission

    def create_project_score_submission(self):
        project = self.create_project()
        submission = self.create_project_submission(
            project,
            self.create_user("project-learner@example.com"),
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

    def assert_project_score_list_send(self, expectation):
        self.assertEqual(expectation.result, {"enqueued_count": 1})
        self.assertEqual(expectation.bulk_upsert.call_count, 2)
        expectation.send_list.assert_called_once()
        self.assertEqual(
            DatamailerOutboxEvent.objects.filter(
                event_type="recipient_list.members_bulk_upsert",
                status=DatamailerOutboxStatus.ACKED,
            ).count(),
            2,
        )
        self.assertEqual(
            expectation.send_list.call_args.args[0],
            project_submitters_list_key(expectation.project),
        )
        self.assertNotIn("members", expectation.send_list.call_args.args[1])
        self.assertNotIn("list", expectation.send_list.call_args.args[1])
        self.assertEqual(
            expectation.bulk_upsert.call_args_list[1].args[0],
            project_passed_list_key(expectation.project),
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

    def assert_homework_score_list_send(self, expectation):
        self.assertEqual(expectation.result["enqueued_count"], 1)
        expectation.bulk_upsert.assert_called_once()
        expectation.send_list.assert_called_once()
        self.assertEqual(
            expectation.send_list.call_args.args[0],
            homework_submitters_list_key(expectation.homework),
        )
        self.assertNotIn("members", expectation.send_list.call_args.args[1])
        self.assertNotIn("list", expectation.send_list.call_args.args[1])
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.send_type, DatamailerSendAuditType.RECIPIENT_LIST)
        self.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
        self.assertEqual(
            audit.list_key,
            homework_submitters_list_key(expectation.homework),
        )
        self.assertEqual(audit.template_key, "homework-score-notification")
        self.assertEqual(audit.category_tag, "submission-results")
        self.assertEqual(audit.event, "homework_score_publication")
        self.assertEqual(audit.intended_count, 1)
        self.assertEqual(audit.enqueued_count, 1)
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(
            event.event_type,
            "recipient_list.members_bulk_upsert",
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(
            event.payload["list_key"],
            homework_submitters_list_key(expectation.homework),
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_homework_score_notification_payload_targets_homework_submitters(
        self,
    ):
        homework = self.create_homework()
        user = self.create_user("learner@example.com")
        submission = self.create_homework_submission(
            homework,
            user,
            questions_score=6,
            learning_in_public_score=2,
            faq_score=1,
            total_score=9,
        )

        list_key, payload = homework_score_notification_payload(
            homework
        )

        self.assertEqual(
            list_key, homework_submitters_list_key(homework)
        )
        expectation = ScorePayloadExpectation(
            payload=payload,
            template_key="homework-score-notification",
            idempotency_key="homework-score:ml-zoomcamp-2026:homework-1",
            footer_text="you submitted Homework 1",
            list_type="homework_submitters",
        )
        member = self.assert_score_payload_common(expectation)
        self.assertEqual(
            payload["context"]["scores_url"],
            "https://courses.example.com/ml-zoomcamp-2026/homework/homework-1",
        )
        self.assertEqual(
            payload["context"]["leaderboard_url"],
            "https://courses.example.com/ml-zoomcamp-2026/leaderboard",
        )
        self.assert_homework_score_member(member, submission)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_homework_score_notification_payload_dedupes_student_submissions(
        self,
    ):
        homework, latest_submission = self.create_duplicate_homework_submissions()

        _, payload = homework_score_notification_payload(homework)

        member = self.single_homework_score_member(payload)
        self.assertEqual(
            member["source_object_key"],
            f"homework-submission:{latest_submission.pk}",
        )
        self.assertEqual(member["email"], "learner@example.com")
        self.assertEqual(member["metadata"]["total_score"], 9)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_homework_score_notification_includes_submitters(self):
        homework = self.create_homework()
        user = self.create_user("learner@example.com")
        self.create_homework_submission(homework, user, total_score=9)

        _, payload = homework_score_notification_payload(homework)

        member = self.single_homework_score_member(payload)
        self.assertEqual(member["email"], "learner@example.com")
        self.assertEqual(member["metadata"]["total_score"], 9)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_send_homework_score_notification_uses_list_send(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.return_value = {"updated_count": 0}
        send_list.return_value = {
            "recipient_list": {
                "key": "ml-zoomcamp-2026:@e:@homework:homework-1",
                "active_member_count": 1,
            },
            "template_key": "homework-score-notification",
            "idempotency_key": "homework-score:ml-zoomcamp-2026:homework-1",
            "created_count": 1,
            "enqueued_count": 1,
            "skipped_count": 0,
            "idempotent_replay_count": 0,
        }
        homework = self.create_homework()

        result = send_homework_score_notification(homework)

        expectation = HomeworkScoreListSendExpectation(
            result=result,
            bulk_upsert=bulk_upsert,
            send_list=send_list,
            homework=homework,
        )
        self.assert_homework_score_list_send(expectation)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_score_notification_does_not_send_without_metadata_ack(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.side_effect = requests.RequestException("network error")
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        homework = Homework.objects.create(
            course=course,
            slug="homework-1",
            title="Homework 1",
            due_date="2026-01-01T00:00:00Z",
        )

        result = send_homework_score_notification(homework)

        self.assertIsNone(result)
        send_list.assert_not_called()
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(
            event.event_type,
            "recipient_list.members_bulk_upsert",
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.RETRYING)
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.status, DatamailerSendAuditStatus.FAILED)
        self.assertIn("metadata sync", audit.error)

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_project_score_notification_payload_targets_project_submitters(
        self,
    ):
        project, submission = self.create_project_score_submission()

        list_key, payload = project_score_notification_payload(project)

        self.assertEqual(list_key, project_submitters_list_key(project))
        expectation = ScorePayloadExpectation(
            payload=payload,
            template_key="project-score-notification",
            idempotency_key="project-score:ml-zoomcamp-2026:project-1",
            footer_text="you submitted Project 1",
            list_type="project_submitters",
        )
        member = self.assert_score_payload_common(expectation)
        self.assert_project_score_context(payload)
        self.assert_project_score_member(member, submission)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_project_score_notification_dedupes_student_submissions(self):
        project, latest = self.create_duplicate_project_submissions()

        _, payload = project_score_notification_payload(project)

        self.assert_latest_project_score_member(
            self.single_project_score_member(payload),
            latest,
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_project_passed_recipient_list_payload_targets_passed_outcome(
        self,
    ):
        project, passed_submission = (
            self.create_passed_and_failed_project_submissions()
        )

        list_key, payload = project_passed_recipient_list_payload(project)

        self.assertEqual(list_key, project_passed_list_key(project))
        self.assertEqual(payload["list"]["type"], "custom")
        self.assertEqual(
            payload["list"]["metadata"]["outcome"], "project_passed"
        )
        self.assertEqual(len(payload["members"]), 1)
        member = payload["members"][0]
        self.assertEqual(member["email"], "passed@example.com")
        self.assertEqual(
            member["source_object_key"],
            f"project-submission:{passed_submission.pk}",
        )
        self.assertEqual(member["metadata"]["outcome"], "project_passed")
        self.assertEqual(member["metadata"]["total_score"], 98)
        self.assertTrue(member["metadata"]["passed"])

    @override_settings(**DATAMAILER_SETTINGS)
    def test_project_score_notification_includes_submitters(self):
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        project = Project.objects.create(
            course=course,
            slug="project-1",
            title="Project 1",
            submission_due_date="2026-01-01T00:00:00Z",
            peer_review_due_date="2026-01-08T00:00:00Z",
        )
        user = CustomUser.objects.create_user(
            username="project-learner@example.com",
            email="project-learner@example.com",
            password="test",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
        )
        ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
            github_link="https://github.com/example/project",
            commit_id="abc123",
            total_score=98,
        )

        _, payload = project_score_notification_payload(project)

        self.assertEqual(len(payload["members"]), 1)
        member = payload["members"][0]
        self.assertEqual(member["email"], "project-learner@example.com")
        self.assertEqual(member["metadata"]["total_score"], 98)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_recipient_list_transactional"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_upsert_recipient_list_members"
    )
    def test_send_project_score_notification_bulk_upserts_passed_outcome_before_send(
        self,
        bulk_upsert,
        send_list,
    ):
        bulk_upsert.return_value = {"updated_count": 0}
        send_list.return_value = {"enqueued_count": 1}
        project = self.create_project()
        submission = self.create_project_submission(
            project,
            self.create_user("project-learner@example.com"),
            total_score=98,
            passed=True,
        )

        result = send_project_score_notification(project)

        expectation = ProjectScoreListSendExpectation(
            result=result,
            bulk_upsert=bulk_upsert,
            send_list=send_list,
            project=project,
            submission=submission,
        )
        self.assert_project_score_list_send(expectation)
