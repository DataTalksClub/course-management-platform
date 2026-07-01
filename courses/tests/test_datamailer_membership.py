from dataclasses import dataclass
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from accounts.models import CustomUser
from course_management.datamailer.keys import (
    course_enrolled_list_key,
    course_graduates_list_key,
    homework_submitters_list_key,
    project_passed_list_key,
    project_submitters_list_key,
)
from course_management.datamailer.payloads.base import (
    enrollment_recipient_list_payload,
)
from course_management.datamailer.sync.membership_removals import (
    remove_enrollment_from_datamailer,
    remove_homework_submission_from_datamailer,
    remove_project_submission_from_datamailer,
)
from course_management.datamailer.sync.memberships import (
    sync_enrollment_to_datamailer,
    sync_homework_submission_to_datamailer,
    sync_project_passed_outcome_to_datamailer,
    sync_project_submission_to_datamailer,
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
class UpsertedRecipientMemberExpectation:
    upsert_member: Mock
    list_key: str
    source_object_key: str
    list_type: str


class DatamailerMembershipTest(TestCase):
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

    def create_project_submission_removal_fixture(self):
        project = self.create_project()
        submission = self.create_project_submission(
            project,
            self.create_user("student@example.com"),
            total_score=98,
            passed=True,
        )
        return project, submission

    def create_failed_project_submission_for_passed_outcome(self):
        project = self.create_project()
        submission = self.create_project_submission(
            project,
            self.create_user("student@example.com"),
            total_score=50,
            passed=False,
        )
        return project, submission

    def assert_upserted_recipient_member(self, expectation):
        expectation.upsert_member.assert_called_once()
        self.assertEqual(
            expectation.upsert_member.call_args.args[0],
            expectation.list_key,
        )
        self.assertEqual(
            expectation.upsert_member.call_args.args[1],
            expectation.source_object_key,
        )
        self.assertEqual(
            expectation.upsert_member.call_args.args[2]["list"]["type"],
            expectation.list_type,
        )

    def assert_project_passed_member_upserted(self, upsert_member, project):
        upsert_member.assert_called_once()
        self.assertEqual(
            upsert_member.call_args.args[0],
            project_passed_list_key(project),
        )
        payload = upsert_member.call_args.args[2]
        self.assertEqual(payload["member"]["status"], "active")
        self.assertEqual(
            payload["member"]["metadata"]["outcome"],
            "project_passed",
        )

    def assert_project_passed_member_removed(
        self,
        remove_member,
        project,
        submission,
    ):
        remove_member.assert_called_once()
        self.assertEqual(
            remove_member.call_args.args[0],
            project_passed_list_key(project),
        )
        self.assertEqual(
            remove_member.call_args.args[1],
            f"project-submission:{submission.pk}",
        )

    def assert_homework_submission_member_removed(
        self,
        remove_member,
        homework,
        submission,
    ):
        remove_member.assert_called_once()
        self.assertEqual(
            remove_member.call_args.args[0],
            homework_submitters_list_key(homework),
        )
        self.assertEqual(
            remove_member.call_args.args[1],
            f"homework-submission:{submission.pk}",
        )

    def assert_project_submission_members_removed(
        self,
        remove_member,
        project,
        submission,
    ):
        self.assertEqual(remove_member.call_count, 2)
        list_keys = []
        remove_calls = remove_member.call_args_list
        for call in remove_calls:
            list_key = call.args[0]
            list_keys.append(list_key)
        self.assertEqual(
            list_keys,
            [project_submitters_list_key(project), project_passed_list_key(project)],
        )
        for call in remove_calls:
            self.assertEqual(call.args[1], f"project-submission:{submission.pk}")

    def assert_enrollment_members_removed(self, remove_member, course, enrollment):
        self.assertEqual(remove_member.call_count, 2)
        list_keys = []
        remove_calls = remove_member.call_args_list
        for call in remove_calls:
            list_key = call.args[0]
            list_keys.append(list_key)
        self.assertEqual(
            list_keys,
            [course_enrolled_list_key(course), course_graduates_list_key(course)],
        )

        source_object_keys = []
        for call in remove_calls:
            source_object_key = call.args[1]
            source_object_keys.append(source_object_key)
        expected_source_object_keys = [
            f"user:{enrollment.student_id}",
            f"enrollment:{enrollment.pk}",
        ]
        self.assertEqual(source_object_keys, expected_source_object_keys)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_enrollment_recipient_list_payload_targets_course_enrolled(
        self,
    ):
        user = self.create_user("Student@Example.com")
        course = self.create_ml_course()
        enrollment = self.create_enrollment(user, course)

        member_payload = enrollment_recipient_list_payload(enrollment)

        self.assertEqual(
            member_payload.list_key,
            course_enrolled_list_key(course),
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
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
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
        self.assertEqual(
            upsert_member.call_args.args[0],
            course_enrolled_list_key(course),
        )
        self.assertEqual(
            upsert_member.call_args.args[1],
            f"user:{user.pk}",
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_sync_homework_submission_adds_submitter_member(
        self,
        upsert_contact,
        upsert_member,
    ):
        homework = self.create_homework()
        submission = self.create_homework_submission(
            homework,
            self.create_user("student@example.com"),
        )

        sync_homework_submission_to_datamailer(submission)

        upsert_contact.assert_called_once()
        expectation = UpsertedRecipientMemberExpectation(
            upsert_member=upsert_member,
            list_key=homework_submitters_list_key(homework),
            source_object_key=f"homework-submission:{submission.pk}",
            list_type="homework_submitters",
        )
        self.assert_upserted_recipient_member(expectation)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
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
        expectation = UpsertedRecipientMemberExpectation(
            upsert_member=upsert_member,
            list_key=project_submitters_list_key(project),
            source_object_key=f"project-submission:{submission.pk}",
            list_type="project_submitters",
        )
        self.assert_upserted_recipient_member(expectation)

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.remove_recipient_list_member"
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
        "course_management.datamailer.client.DatamailerClient.remove_recipient_list_member"
    )
    def test_remove_homework_submission_deletes_submitter_member(
        self,
        remove_member,
    ):
        homework = self.create_homework()
        submission = self.create_homework_submission(
            homework,
            self.create_user("student@example.com"),
        )

        remove_homework_submission_from_datamailer(submission)

        self.assert_homework_submission_member_removed(
            remove_member,
            homework,
            submission,
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.remove_recipient_list_member"
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
