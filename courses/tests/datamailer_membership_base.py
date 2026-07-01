from dataclasses import dataclass
from unittest.mock import Mock

from django.test import TestCase

from accounts.models import CustomUser
from course_management.datamailer.keys import (
    course_enrolled_list_key,
    course_graduates_list_key,
    homework_submitters_list_key,
    project_passed_list_key,
    project_submitters_list_key,
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


class DatamailerMembershipBase(TestCase):
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
        enrollment = self.create_enrollment(user, project.course)
        defaults = {
            "project": project,
            "student": user,
            "enrollment": enrollment,
            "github_link": "https://github.com/example/project",
            "commit_id": "abc123",
        }
        defaults.update(overrides)
        return ProjectSubmission.objects.create(**defaults)

    def create_project_submission_removal_fixture(self):
        project = self.create_project()
        user = self.create_user("student@example.com")
        submission = self.create_project_submission(
            project,
            user,
            total_score=98,
            passed=True,
        )
        return project, submission

    def create_failed_project_submission_for_passed_outcome(self):
        project = self.create_project()
        user = self.create_user("student@example.com")
        submission = self.create_project_submission(
            project,
            user,
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
        list_key = project_passed_list_key(project)
        self.assertEqual(
            upsert_member.call_args.args[0],
            list_key,
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
        list_key = project_passed_list_key(project)
        self.assertEqual(
            remove_member.call_args.args[0],
            list_key,
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
        list_key = homework_submitters_list_key(homework)
        self.assertEqual(
            remove_member.call_args.args[0],
            list_key,
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
        project_submitters_key = project_submitters_list_key(project)
        project_passed_key = project_passed_list_key(project)
        expected_list_keys = [project_submitters_key, project_passed_key]
        self.assertEqual(
            list_keys,
            expected_list_keys,
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
        course_enrolled_key = course_enrolled_list_key(course)
        course_graduates_key = course_graduates_list_key(course)
        expected_list_keys = [course_enrolled_key, course_graduates_key]
        self.assertEqual(
            list_keys,
            expected_list_keys,
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
