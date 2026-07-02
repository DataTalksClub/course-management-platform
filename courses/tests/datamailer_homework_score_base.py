from dataclasses import dataclass
from datetime import timedelta
from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)
from course_management.datamailer.keys import homework_submitters_list_key
from courses.models import Course, Enrollment, Homework, Submission


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
class HomeworkScoreListSendExpectation:
    result: dict
    bulk_upsert: Mock
    send_list: Mock
    homework: Homework


class DatamailerHomeworkScoreTestBase(TestCase):
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

    def assert_homework_score_context_urls(self, payload):
        self.assertEqual(
            payload["context"]["scores_url"],
            "https://courses.example.com/ml-zoomcamp-2026/homework/homework-1",
        )
        self.assertEqual(
            payload["context"]["leaderboard_url"],
            "https://courses.example.com/ml-zoomcamp-2026/leaderboard",
        )

    def single_homework_score_member(self, payload):
        self.assertEqual(len(payload["members"]), 1)
        return payload["members"][0]

    def create_scored_homework_submission(self):
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
        return homework, submission

    def homework_score_payload_expectation(self, payload):
        return ScorePayloadExpectation(
            payload=payload,
            template_key="homework-score-notification",
            idempotency_key="homework-score:ml-zoomcamp-2026:homework-1",
            footer_text="you submitted Homework 1",
            list_type="homework_submitters",
        )

    def create_duplicate_homework_submissions(self):
        homework = self.create_homework()
        user = self.create_user("learner@example.com")
        enrollment = self.create_enrollment(user, homework.course)
        earlier_submission_time = timezone.now() - timedelta(days=1)
        self.create_homework_submission(
            homework,
            user,
            enrollment=enrollment,
            submitted_at=earlier_submission_time,
            total_score=4,
        )
        latest_submission_time = timezone.now()
        latest_submission = self.create_homework_submission(
            homework,
            user,
            enrollment=enrollment,
            submitted_at=latest_submission_time,
            total_score=9,
        )
        return homework, latest_submission

    def assert_homework_score_list_send(self, expectation):
        self.assertEqual(expectation.result["enqueued_count"], 1)
        self.assert_homework_score_client_calls(expectation)
        self.assert_homework_score_send_audit(expectation.homework)
        self.assert_homework_score_outbox_event(expectation.homework)

    def assert_homework_score_client_calls(self, expectation):
        expectation.bulk_upsert.assert_called_once()
        expectation.send_list.assert_called_once()
        expected_list_key = homework_submitters_list_key(
            expectation.homework
        )
        self.assertEqual(
            expectation.send_list.call_args.args[0],
            expected_list_key,
        )
        self.assertNotIn("members", expectation.send_list.call_args.args[1])
        self.assertNotIn("list", expectation.send_list.call_args.args[1])

    def assert_homework_score_send_audit(self, homework):
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.send_type, DatamailerSendAuditType.RECIPIENT_LIST)
        self.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
        expected_list_key = homework_submitters_list_key(homework)
        self.assertEqual(
            audit.list_key,
            expected_list_key,
        )
        self.assertEqual(audit.template_key, "homework-score-notification")
        self.assertEqual(audit.category_tag, "submission-results")
        self.assertEqual(audit.event, "homework_score_publication")
        self.assertEqual(audit.intended_count, 1)
        self.assertEqual(audit.enqueued_count, 1)

    def assert_homework_score_outbox_event(self, homework):
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(
            event.event_type,
            "recipient_list.members_bulk_upsert",
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        expected_list_key = homework_submitters_list_key(homework)
        self.assertEqual(
            event.payload["list_key"],
            expected_list_key,
        )
