from unittest.mock import patch

from django.test import override_settings

from course_management.datamailer.sync.memberships import (
    sync_project_passed_outcome_to_datamailer,
)
from courses.tests.datamailer_membership_base import (
    DATAMAILER_SETTINGS,
    DatamailerMembershipBase,
)


class DatamailerMembershipOutcomeTest(DatamailerMembershipBase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_sync_project_passed_outcome_upserts_passed_member(
        self,
        upsert_contact,
        upsert_member,
    ):
        project, passed_submission = self.create_project_submission_removal_fixture()

        sync_project_passed_outcome_to_datamailer(passed_submission)

        upsert_contact.assert_called_once()
        self.assert_project_passed_member_upserted(upsert_member, project)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.remove_recipient_list_member"
    )
    def test_sync_project_passed_outcome_removes_failed_member(
        self,
        remove_member,
    ):
        project, submission = (
            self.create_failed_project_submission_for_passed_outcome()
        )

        sync_project_passed_outcome_to_datamailer(submission)

        self.assert_project_passed_member_removed(
            remove_member,
            project,
            submission,
        )
