from django.test import override_settings

from course_management.datamailer.keys import project_submitters_list_key
from course_management.datamailer.payloads.project_scores import (
    project_score_notification_payload,
)
from courses.tests.datamailer_project_score_base import (
    DATAMAILER_SETTINGS,
    DatamailerProjectScoreTestBase,
    ScorePayloadExpectation,
)


class DatamailerProjectScoreTest(DatamailerProjectScoreTestBase):
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

        project_submitters_key = project_submitters_list_key(project)
        self.assertEqual(list_key, project_submitters_key)
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

        member = self.single_project_score_member(payload)
        self.assert_latest_project_score_member(
            member,
            latest,
        )

    @override_settings(**DATAMAILER_SETTINGS)
    def test_project_score_notification_includes_submitters(self):
        project, _ = self.create_project_score_submission()

        _, payload = project_score_notification_payload(project)

        member = self.single_project_score_member(payload)
        self.assertEqual(member["email"], "project-learner@example.com")
        self.assertEqual(member["metadata"]["total_score"], 98)
