from unittest.mock import patch

from django.test import override_settings

from course_management.datamailer.sync.membership_removals import (
    remove_enrollment_from_datamailer,
    remove_homework_submission_from_datamailer,
    remove_project_submission_from_datamailer,
)
from courses.tests.datamailer_membership_base import (
    DATAMAILER_SETTINGS,
    DatamailerMembershipBase,
)


class DatamailerMembershipRemovalTest(DatamailerMembershipBase):
    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListClient.remove_recipient_list_member"
    )
    def test_remove_enrollment_removes_enrolled_and_graduate_members(
        self,
        remove_member,
    ):
        user = self.create_user("student@example.com")
        course = self.create_ml_course()
        enrollment = self.create_enrollment(
            user,
            course,
            certificate_url="/certificates/student.pdf",
        )

        remove_enrollment_from_datamailer(enrollment)

        self.assert_enrollment_members_removed(remove_member, course, enrollment)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListClient.remove_recipient_list_member"
    )
    def test_remove_homework_submission_deletes_submitter_member(
        self,
        remove_member,
    ):
        homework = self.create_homework()
        user = self.create_user("student@example.com")
        submission = self.create_homework_submission(
            homework,
            user,
        )

        remove_homework_submission_from_datamailer(submission)

        self.assert_homework_submission_member_removed(
            remove_member,
            homework,
            submission,
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListClient.remove_recipient_list_member"
    )
    def test_remove_project_submission_removes_submitter_and_passed_members(
        self,
        remove_member,
    ):
        project, submission = self.create_project_submission_removal_fixture()

        remove_project_submission_from_datamailer(submission)

        self.assert_project_submission_members_removed(
            remove_member,
            project,
            submission,
        )
