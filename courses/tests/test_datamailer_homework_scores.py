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
from course_management.datamailer.keys import homework_submitters_list_key
from course_management.datamailer.payloads import (
    homework_score_notification_payload,
)
from course_management.datamailer.sync import send_homework_score_notification
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


class DatamailerHomeworkScoreTest(TestCase):
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

    def single_homework_score_member(self, payload):
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
        homework = self.create_homework()

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
