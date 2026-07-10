from unittest.mock import patch

from django.test import override_settings

from course_management.datamailer.keys import (
    course_enrolled_list_key,
    homework_submitters_list_key,
    project_submitters_list_key,
)
from course_management.datamailer.payloads.base import (
    enrollment_recipient_list_payload,
)
from course_management.datamailer.sync.memberships import (
    sync_enrollment_to_datamailer,
    sync_homework_submission_to_datamailer,
    sync_project_submission_to_datamailer,
)
from courses.tests.datamailer_membership_base import (
    DATAMAILER_SETTINGS,
    DatamailerMembershipBase,
    UpsertedRecipientMemberExpectation,
)


class DatamailerMembershipTest(DatamailerMembershipBase):
    @override_settings(**DATAMAILER_SETTINGS)
    def test_enrollment_recipient_list_payload_targets_course_enrolled(
        self,
    ):
        user = self.create_user("Student@Example.com")
        course = self.create_ml_course()
        enrollment = self.create_enrollment(user, course)

        member_payload = enrollment_recipient_list_payload(enrollment)

        course_enrolled_key = course_enrolled_list_key(course)
        self.assertEqual(
            member_payload.list_key,
            course_enrolled_key,
        )
        self.assertEqual(member_payload.source_object_key, f"user:{user.pk}")
        payload = member_payload.payload
        self.assertEqual(payload["list"]["type"], "custom")
        self.assertEqual(
            payload["list"]["name"],
            "ML Zoomcamp 2026 enrolled learners",
        )
        self.assertEqual(
            payload["member"]["email"],
            "student@example.com",
        )
        self.assertEqual(
            payload["member"]["metadata"]["enrollment_id"],
            enrollment.pk,
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.upsert"
    )
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.upsert_contact"
    )
    def test_sync_enrollment_adds_contact_and_enrolled_member(
        self,
        upsert_contact,
        upsert_member,
    ):
        user = self.create_user("student@example.com")
        course = self.create_ml_course()
        enrollment = self.create_enrollment(user, course)

        sync_enrollment_to_datamailer(enrollment)

        upsert_contact.assert_called_once()
        upsert_member.assert_called_once()
        course_enrolled_key = course_enrolled_list_key(course)
        self.assertEqual(
            upsert_member.call_args.args[0],
            course_enrolled_key,
        )
        self.assertEqual(
            upsert_member.call_args.args[1],
            f"user:{user.pk}",
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.upsert"
    )
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.upsert_contact"
    )
    def test_sync_homework_submission_adds_submitter_member(
        self,
        upsert_contact,
        upsert_member,
    ):
        homework = self.create_homework()
        user = self.create_user("student@example.com")
        submission = self.create_homework_submission(
            homework,
            user,
        )

        sync_homework_submission_to_datamailer(submission)

        upsert_contact.assert_called_once()
        list_key = homework_submitters_list_key(homework)
        expectation = UpsertedRecipientMemberExpectation(
            upsert_member=upsert_member,
            list_key=list_key,
            source_object_key=f"homework-submission:{submission.pk}",
            list_type="homework_submitters",
        )
        self.assert_upserted_recipient_member(expectation)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.upsert"
    )
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.upsert_contact"
    )
    def test_sync_project_submission_adds_submitter_member(
        self,
        upsert_contact,
        upsert_member,
    ):
        user = self.create_user("student@example.com")
        project = self.create_project()
        submission = self.create_project_submission(
            project,
            user,
            commit_id="a" * 40,
        )

        sync_project_submission_to_datamailer(submission)

        upsert_contact.assert_called_once()
        list_key = project_submitters_list_key(project)
        expectation = UpsertedRecipientMemberExpectation(
            upsert_member=upsert_member,
            list_key=list_key,
            source_object_key=f"project-submission:{submission.pk}",
            list_type="project_submitters",
        )
        self.assert_upserted_recipient_member(expectation)
