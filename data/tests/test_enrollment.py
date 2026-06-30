"""
Tests for enrollment-related data API views.

Tests for enrollment-related data views and helpers.
"""

import json
import random
from dataclasses import dataclass, field
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from courses.models import (
    Course,
    Project,
    ProjectSubmission,
    Enrollment,
)

from accounts.models import CustomUser, Token

from api.views.enrollment_exports import get_passed_enrollments


@dataclass(frozen=True)
class PassedProjectSubmissionData:
    project: Project
    student: CustomUser
    enrollment: Enrollment
    commit_id: str


@dataclass(frozen=True)
class PassedEnrollmentExpectation:
    passed_submissions: list[ProjectSubmission]
    min_projects: int
    expected_enrollments: list[Enrollment]
    missing_enrollments: list[Enrollment] = field(default_factory=list)


@dataclass(frozen=True)
class CertificateUpdateExpectation:
    result: dict
    success: bool
    updated_count: int
    error_count: int | None = None


@dataclass(frozen=True)
class CertificateNotificationScenario:
    data: dict
    second_enrollment: Enrollment


class EnrollmentDataAPITestCase(TestCase):
    """Tests for enrollment-related data API endpoints."""

    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="testuser@example.com",
            password="password",
        )
        self.token = Token.objects.create(user=self.user)

        self.course = Course.objects.create(
            title="Test Course", slug="test-course"
        )

        self.enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
        )

        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
        )

    def require_two_projects_to_pass(self):
        self.course.min_projects_to_pass = 2
        self.course.save()

    def configure_certificate_user(self):
        self.user.email = "student1@example.com"
        self.user.certificate_name = "Student One"
        self.user.save()

    def create_certificate_user(self, username, email, certificate_name):
        return CustomUser.objects.create(
            username=username,
            email=email,
            password="pass",
            certificate_name=certificate_name,
        )

    def create_saved_project(self, slug, title):
        return Project.objects.create(
            course=self.course,
            slug=slug,
            title=title,
            description="Description",
            submission_due_date=timezone.now()
            + timezone.timedelta(days=7),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )

    def create_passed_project_submission(
        self,
        data: PassedProjectSubmissionData,
    ):
        ProjectSubmission.objects.create(
            project=data.project,
            student=data.student,
            enrollment=data.enrollment,
            github_link="https://httpbin.org/status/200",
            commit_id=data.commit_id,
            passed=True,
        )

    def create_graduate_view_scenario(self):
        self.require_two_projects_to_pass()
        self.configure_certificate_user()
        other_user = self.create_certificate_user(
            username="student2",
            email="student2@example.com",
            certificate_name="Student Two",
        )
        other_enrollment = Enrollment.objects.create(
            student=other_user,
            course=self.course,
        )
        project1 = self.create_saved_project("project1", "Project 1")
        project2 = self.create_saved_project("project2", "Project 2")
        first_submission_data = PassedProjectSubmissionData(
            project=project1,
            student=self.user,
            enrollment=self.enrollment,
            commit_id="1111",
        )
        self.create_passed_project_submission(first_submission_data)
        second_submission_data = PassedProjectSubmissionData(
            project=project2,
            student=self.user,
            enrollment=self.enrollment,
            commit_id="2222",
        )
        self.create_passed_project_submission(second_submission_data)
        other_submission_data = PassedProjectSubmissionData(
            project=project1,
            student=other_user,
            enrollment=other_enrollment,
            commit_id="3333",
        )
        self.create_passed_project_submission(other_submission_data)

    def graduates_url(self):
        return reverse(
            "api_course_graduates",
            kwargs={"course_slug": self.course.slug},
        )

    def test_graduate_data_view(self):
        """Test that only students who passed enough projects are returned."""
        self.create_graduate_view_scenario()

        response = self.client.get(self.graduates_url())

        self.assertEqual(response.status_code, 200)
        response_json = response.json()
        graduates = response_json["graduates"]

        self.assertEqual(len(graduates), 1)

        first_graduate = graduates[0]
        self.assertEqual(first_graduate["email"], self.user.email)
        self.assertEqual(
            first_graduate["name"], self.user.certificate_name
        )

    def create_test_project(self, slug, title):
        return Project(
            course=self.course,
            slug=slug,
            title=title,
            description="Description",
            submission_due_date=timezone.now()
            + timezone.timedelta(days=7),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )

    def create_project_submission(self, project, student, enrollment):
        commit_id = "".join(random.choices("0123456789abcdef", k=7))

        return ProjectSubmission(
            project=project,
            student=student,
            enrollment=enrollment,
            github_link=f"https://github.com/test{student.username[-1]}",
            commit_id=commit_id,
            passed=True,
        )

    def create_unsaved_student(self, username, email):
        return CustomUser(
            username=username,
            email=email,
        )

    def create_unsaved_enrollment(self, enrollment_id, student):
        return Enrollment(
            id=enrollment_id,
            student=student,
            course=self.course,
        )

    def get_passed_enrollment_scenario(self):
        user2 = self.create_unsaved_student(
            "student2", "student2@example.com"
        )
        user3 = self.create_unsaved_student(
            "student3", "student3@example.com"
        )
        user4 = self.create_unsaved_student(
            "student4", "student4@example.com"
        )
        enrollment2 = self.create_unsaved_enrollment(2, user2)
        enrollment3 = self.create_unsaved_enrollment(3, user3)
        enrollment4 = self.create_unsaved_enrollment(4, user4)
        project1 = self.create_test_project("p1", "P1")
        project2 = self.create_test_project("p2", "P2")
        project3 = self.create_test_project("p3", "P3")

        passed_submissions = [
            self.create_project_submission(
                project1, self.user, self.enrollment
            ),
            self.create_project_submission(
                project2, self.user, self.enrollment
            ),
            self.create_project_submission(project1, user2, enrollment2),
            self.create_project_submission(project1, user3, enrollment3),
            self.create_project_submission(project2, user3, enrollment3),
            self.create_project_submission(project3, user3, enrollment3),
        ]
        return passed_submissions, enrollment2, enrollment3, enrollment4

    def assert_enrollments_for_min_projects(
        self,
        data: PassedEnrollmentExpectation,
    ):
        result = get_passed_enrollments(
            data.passed_submissions,
            data.min_projects,
        )
        self.assertEqual(len(result), len(data.expected_enrollments))
        for enrollment in data.expected_enrollments:
            self.assertIn(enrollment, result)
        for enrollment in data.missing_enrollments:
            self.assertNotIn(enrollment, result)
        return result

    def test_get_passed_enrollments(self):
        """Test the get_passed_enrollments function with various scenarios."""
        passed_submissions, enrollment2, enrollment3, enrollment4 = (
            self.get_passed_enrollment_scenario()
        )

        two_project_expectation = PassedEnrollmentExpectation(
            passed_submissions=passed_submissions,
            min_projects=2,
            expected_enrollments=[self.enrollment, enrollment3],
            missing_enrollments=[enrollment2, enrollment4],
        )
        self.assert_enrollments_for_min_projects(two_project_expectation)
        one_project_expectation = PassedEnrollmentExpectation(
            passed_submissions=passed_submissions,
            min_projects=1,
            expected_enrollments=[
                self.enrollment,
                enrollment2,
                enrollment3,
            ],
            missing_enrollments=[enrollment4],
        )
        self.assert_enrollments_for_min_projects(one_project_expectation)
        three_project_expectation = PassedEnrollmentExpectation(
            passed_submissions=passed_submissions,
            min_projects=3,
            expected_enrollments=[enrollment3],
        )
        result = self.assert_enrollments_for_min_projects(
            three_project_expectation
        )
        self.assertEqual(result[0], enrollment3)
        self.assertEqual(len(get_passed_enrollments(passed_submissions, 4)), 0)
        self.assertEqual(len(get_passed_enrollments([], 1)), 0)
        with self.assertRaises(AssertionError):
            get_passed_enrollments(passed_submissions, 0)

    def create_enrolled_user(self, username, email, **enrollment_kwargs):
        user = CustomUser.objects.create(
            username=username,
            email=email,
            password="password",
        )
        enrollment = Enrollment.objects.create(
            student=user,
            course=self.course,
            **enrollment_kwargs,
        )
        return user, enrollment

    def certificate_url(self):
        return reverse(
            "api_course_certificates",
            kwargs={"course_slug": self.course.slug},
        )

    def post_certificates(self, data):
        return self.client.post(
            self.certificate_url(),
            json.dumps(data),
            content_type="application/json",
        )

    def certificate_payload(self, certificates):
        return {"certificates": certificates}

    def mixed_certificate_payload(self, second_user, other_user):
        return self.certificate_payload(
            [
                {
                    "email": self.user.email,
                    "certificate_path": "/certificates/first.pdf",
                },
                {
                    "email": second_user.email,
                    "certificate_path": "/certificates/second.pdf",
                },
                {
                    "email": "missing@example.com",
                    "certificate_path": "/certificates/missing.pdf",
                },
                {
                    "email": other_user.email,
                    "certificate_path": "/certificates/other.pdf",
                },
                {"email": self.user.email},
            ]
        )

    def assert_certificate_update_result(
        self,
        data: CertificateUpdateExpectation,
    ):
        self.assertEqual(data.result["success"], data.success)
        self.assertEqual(data.result["updated_count"], data.updated_count)
        if data.error_count is not None:
            self.assertEqual(data.result["error_count"], data.error_count)

    def assert_certificate_url(self, enrollment, certificate_url):
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.certificate_url, certificate_url)

    def certificate_notification_scenario(self):
        second_user, second_enrollment = self.create_enrolled_user(
            "seconduser",
            "second@example.com",
            certificate_url="/certificates/old.pdf",
        )
        data = self.certificate_payload(
            [
                {
                    "email": self.user.email,
                    "certificate_path": "/certificates/first.pdf",
                },
                {
                    "email": second_user.email,
                    "certificate_path": "/certificates/second.pdf",
                },
            ]
        )
        return CertificateNotificationScenario(
            data=data,
            second_enrollment=second_enrollment,
        )

    def post_certificates_with_callbacks(self, data):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_certificates(data)
        return response

    def assert_successful_certificate_notification_result(self, response):
        self.assertEqual(response.status_code, 200)
        result = response.json()
        expectation = CertificateUpdateExpectation(
            result=result,
            success=True,
            updated_count=2,
        )
        self.assert_certificate_update_result(expectation)

    def assert_certificate_notification_urls(self, second_enrollment):
        self.assert_certificate_url(
            self.enrollment, "/certificates/first.pdf"
        )
        self.assert_certificate_url(
            second_enrollment, "/certificates/second.pdf"
        )

    def assert_certificate_notification_sent(self, send_notification):
        send_notification.assert_called_once()
        notified_enrollment = send_notification.call_args.args[0]
        self.assertEqual(notified_enrollment.id, self.enrollment.id)
        self.assertEqual(
            notified_enrollment.certificate_url,
            "/certificates/first.pdf",
        )

    def test_bulk_update_enrollment_certificates_view(self):
        """Test bulk updating enrollment certificate URLs."""
        second_user, second_enrollment = self.create_enrolled_user(
            "seconduser", "second@example.com"
        )
        other_user = CustomUser.objects.create(
            username="otheruser",
            email="other@example.com",
            password="password",
        )
        data = self.mixed_certificate_payload(second_user, other_user)

        response = self.post_certificates(data)

        self.assertEqual(response.status_code, 200)
        result = response.json()
        expectation = CertificateUpdateExpectation(
            result=result,
            success=False,
            updated_count=2,
            error_count=3,
        )
        self.assert_certificate_update_result(expectation)
        error_codes = set()
        for error in result["errors"]:
            error_codes.add(error["code"])
        self.assertEqual(
            error_codes,
            {"missing_fields", "not_enrolled", "user_not_found"},
        )
        self.assert_certificate_url(
            self.enrollment, "/certificates/first.pdf"
        )
        self.assert_certificate_url(
            second_enrollment, "/certificates/second.pdf"
        )

        response = self.client.get(self.certificate_url())
        self.assertEqual(response.status_code, 405)

    def test_bulk_update_enrollment_certificates_accepts_array_payload(
        self,
    ):
        """Test bulk certificate updates with a bare array payload."""
        data = [
            {
                "email": self.user.email,
                "certificate_path": "/certificates/array.pdf",
            }
        ]

        response = self.post_certificates(data)

        self.assertEqual(response.status_code, 200)
        result = response.json()
        expectation = CertificateUpdateExpectation(
            result=result,
            success=True,
            updated_count=1,
            error_count=0,
        )
        self.assert_certificate_update_result(expectation)
        self.assert_certificate_url(
            self.enrollment, "/certificates/array.pdf"
        )

    @patch(
        "api.views.enrollment_exports."
        "send_certificate_availability_notification"
    )
    def test_bulk_update_enrollment_certificates_sends_new_certificate_notifications(
        self,
        send_notification,
    ):
        scenario = self.certificate_notification_scenario()

        response = self.post_certificates_with_callbacks(scenario.data)

        self.assert_successful_certificate_notification_result(response)
        self.assert_certificate_notification_urls(
            scenario.second_enrollment
        )
        self.assert_certificate_notification_sent(send_notification)
