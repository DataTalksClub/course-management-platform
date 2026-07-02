from django.test import override_settings

from course_management.datamailer.keys import homework_submitters_list_key
from course_management.datamailer.payloads.homework_scores import (
    homework_score_notification_payload,
)
from courses.tests.datamailer_homework_score_base import (
    DATAMAILER_SETTINGS,
    DatamailerHomeworkScoreTestBase,
)


class DatamailerHomeworkScorePayloadTest(DatamailerHomeworkScoreTestBase):
    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_homework_score_notification_payload_targets_homework_submitters(
        self,
    ):
        homework, submission = self.create_scored_homework_submission()

        list_key, payload = homework_score_notification_payload(
            homework
        )

        expected_list_key = homework_submitters_list_key(homework)
        self.assertEqual(
            list_key, expected_list_key
        )
        expectation = self.homework_score_payload_expectation(payload)
        member = self.assert_score_payload_common(expectation)
        self.assert_homework_score_context_urls(payload)
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
