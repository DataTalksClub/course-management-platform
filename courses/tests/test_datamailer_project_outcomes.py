from unittest.mock import patch

from django.test import override_settings

from course_management.datamailer.keys import project_passed_list_key
from course_management.datamailer.payloads.project_outcomes import (
    project_passed_recipient_list_payload,
)
from course_management.datamailer.sync.score_notifications import (
    send_project_score_notification,
)
from courses.tests.datamailer_project_score_base import (
    DATAMAILER_SETTINGS,
    DatamailerProjectScoreTestBase,
    ProjectScoreListSendExpectation,
)


class DatamailerProjectOutcomeTest(DatamailerProjectScoreTestBase):
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

        project_passed_key = project_passed_list_key(project)
        self.assertEqual(list_key, project_passed_key)
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
        user = self.create_user("project-learner@example.com")
        submission = self.create_project_submission(
            project,
            user,
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
