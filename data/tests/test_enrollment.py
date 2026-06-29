"""
Tests for enrollment-related data API views.

Tests for enrollment-related data views and helpers.
"""

import json
import random
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
        self, project, student, enrollment, commit_id
    ):
        ProjectSubmission.objects.create(
            project=project,
            student=student,
            enrollment=enrollment,
            github_link="https://httpbin.org/status/200",
            commit_id=commit_id,
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
        self.create_passed_project_submission(
            project1, self.user, self.enrollment, "1111"
        )
        self.create_passed_project_submission(
            project2, self.user, self.enrollment, "2222"
        )
        self.create_passed_project_submission(
            project1, other_user, other_enrollment, "3333"
        )

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
        passed_submissions,
        min_projects,
        expected_enrollments,
        missing_enrollments=(),
    ):
        result = get_passed_enrollments(passed_submissions, min_projects)
        self.assertEqual(len(result), len(expected_enrollments))
        for enrollment in expected_enrollments:
            self.assertIn(enrollment, result)
        for enrollment in missing_enrollments:
            self.assertNotIn(enrollment, result)
        return result

    def test_get_passed_enrollments(self):
        """Test the get_passed_enrollments function with various scenarios."""
        passed_submissions, enrollment2, enrollment3, enrollment4 = (
            self.get_passed_enrollment_scenario()
        )

        self.assert_enrollments_for_min_projects(
            passed_submissions,
            2,
            [self.enrollment, enrollment3],
            [enrollment2, enrollment4],
        )
        self.assert_enrollments_for_min_projects(
            passed_submissions,
            1,
            [self.enrollment, enrollment2, enrollment3],
            [enrollment4],
        )
        result = self.assert_enrollments_for_min_projects(
            passed_submissions,
            3,
            [enrollment3],
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
        result,
        success,
        updated_count,
        error_count=None,
    ):
        self.assertEqual(result["success"], success)
        self.assertEqual(result["updated_count"], updated_count)
        if error_count is not None:
            self.assertEqual(result["error_count"], error_count)

    def assert_certificate_url(self, enrollment, certificate_url):
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.certificate_url, certificate_url)

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
        self.assert_certificate_update_result(result, False, 2, 3)
        error_codes = {error["code"] for error in result["errors"]}
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
        self.assert_certificate_update_result(result, True, 1, 0)
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

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_certificates(data)

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assert_certificate_update_result(result, True, 2)
        self.assert_certificate_url(
            self.enrollment, "/certificates/first.pdf"
        )
        self.assert_certificate_url(
            second_enrollment, "/certificates/second.pdf"
        )
        send_notification.assert_called_once()
        notified_enrollment = send_notification.call_args.args[0]
        self.assertEqual(notified_enrollment.id, self.enrollment.id)
        self.assertEqual(
            notified_enrollment.certificate_url,
            "/certificates/first.pdf",
        )
