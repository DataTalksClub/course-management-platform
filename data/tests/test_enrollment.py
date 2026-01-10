"""
Tests for enrollment-related data API views.

Tests for graduates_data_view, update_enrollment_certificate_view, and get_passed_enrollments helper.
"""

import json
import random

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

from data.views.enrollment import get_passed_enrollments


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

    def test_graduate_data_view(self):
        """Test that only students who passed enough projects are returned."""
        self.course.min_projects_to_pass = 2
        self.course.save()

        self.user.email = "student1@example.com"
        self.user.save()
        self.enrollment.certificate_name = "Student One"
        self.enrollment.save()

        other_user = CustomUser.objects.create(
            username="student2",
            email="student2@example.com",
            password="pass",
        )
        other_enrollment = Enrollment.objects.create(
            student=other_user,
            course=self.course,
            certificate_name="Student Two",
        )

        project1 = Project.objects.create(
            course=self.course,
            slug="project1",
            title="Project 1",
            description="Description",
            submission_due_date=timezone.now()
            + timezone.timedelta(days=7),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )
        project2 = Project.objects.create(
            course=self.course,
            slug="project2",
            title="Project 2",
            description="Description",
            submission_due_date=timezone.now()
            + timezone.timedelta(days=7),
            peer_review_due_date=timezone.now()
            + timezone.timedelta(days=14),
        )

        ProjectSubmission.objects.create(
            project=project1,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://httpbin.org/status/200",
            commit_id="1111",
            passed=True,
        )
        ProjectSubmission.objects.create(
            project=project2,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://httpbin.org/status/200",
            commit_id="2222",
            passed=True,
        )
        ProjectSubmission.objects.create(
            project=project1,
            student=other_user,
            enrollment=other_enrollment,
            github_link="https://httpbin.org/status/200",
            commit_id="3333",
            passed=True,
        )

        url = reverse(
            "data_graduates",
            kwargs={"course_slug": self.course.slug},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_json = response.json()
        graduates = response_json["graduates"]

        self.assertEqual(len(graduates), 1)

        first_graduate = graduates[0]
        self.assertEqual(first_graduate["email"], self.user.email)
        self.assertEqual(
            first_graduate["name"], self.enrollment.certificate_name
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

    def test_get_passed_enrollments(self):
        """Test the get_passed_enrollments function with various scenarios."""

        # Create additional users and enrollments for testing
        user2 = CustomUser(
            username="student2",
            email="student2@example.com",
        )
        user3 = CustomUser(
            username="student3",
            email="student3@example.com",
        )
        user4 = CustomUser(
            username="student4",
            email="student4@example.com",
        )

        enrollment2 = Enrollment(
            id=2,
            student=user2,
            course=self.course,
        )
        enrollment3 = Enrollment(
            id=3,
            student=user3,
            course=self.course,
        )
        enrollment4 = Enrollment(
            id=4,
            student=user4,
            course=self.course,
        )

        project1 = self.create_test_project("p1", "P1")
        project2 = self.create_test_project("p2", "P2")
        project3 = self.create_test_project("p3", "P3")

        # User 1: Passes 2 projects (should be included with min_projects=2)
        submission1_user1 = self.create_project_submission(
            project1, self.user, self.enrollment
        )
        submission2_user1 = self.create_project_submission(
            project2, self.user, self.enrollment
        )

        # User 2: Passes 1 project (should NOT be included with min_projects=2)
        submission1_user2 = self.create_project_submission(
            project1, user2, enrollment2
        )

        # User 3: Passes 3 projects (should be included with min_projects=2)
        submission1_user3 = self.create_project_submission(
            project1, user3, enrollment3
        )
        submission2_user3 = self.create_project_submission(
            project2, user3, enrollment3
        )
        submission3_user3 = self.create_project_submission(
            project3, user3, enrollment3
        )

        passed_submissions = [
            submission1_user1,
            submission2_user1,
            submission1_user2,
            submission1_user3,
            submission2_user3,
            submission3_user3,
        ]

        # Test with min_projects=2
        result = get_passed_enrollments(passed_submissions, 2)

        # Should return 2 enrollments (user1 with 2 passed, user3 with 3 passed)
        self.assertEqual(len(result), 2)

        # Check that the correct enrollments are returned
        self.assertIn(self.enrollment, result)  # User 1
        self.assertIn(enrollment3, result)  # User 3
        self.assertNotIn(enrollment2, result)  # User 2 (only 1 passed)
        self.assertNotIn(enrollment4, result)  # User 4 (no submissions)

        # Test with min_projects=1
        result = get_passed_enrollments(passed_submissions, 1)

        # Should return 3 enrollments (all users with at least 1 passed)
        self.assertEqual(len(result), 3)

        # Check that the correct enrollments are returned
        self.assertIn(self.enrollment, result)  # User 1
        self.assertIn(enrollment2, result)  # User 2
        self.assertIn(enrollment3, result)  # User 3
        self.assertNotIn(enrollment4, result)  # User 4 (no submissions)

        # Test with min_projects=3
        result = get_passed_enrollments(passed_submissions, 3)

        # Should return 1 enrollment (only user3 with 3 passed)
        self.assertEqual(len(result), 1)

        # Check that only user3's enrollment is returned
        self.assertEqual(result[0], enrollment3)

        # Test with min_projects=4
        result = get_passed_enrollments(passed_submissions, 4)

        # Should return 0 enrollments (no user has 4 passed projects)
        self.assertEqual(len(result), 0)

        # Test with empty submissions list
        result = get_passed_enrollments([], 1)
        self.assertEqual(len(result), 0)

        # Test with min_projects=0
        with self.assertRaises(AssertionError):
            result = get_passed_enrollments(passed_submissions, 0)

    def test_update_enrollment_certificate_view(self):
        """Test updating enrollment certificate URL."""
        url = reverse(
            "data_update_certificate",
            kwargs={"course_slug": self.course.slug},
        )

        # Test successful update
        data = {
            "email": self.user.email,
            "certificate_path": "/certificates/test-certificate.pdf",
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])
        self.assertEqual(
            result["certificate_url"],
            "/certificates/test-certificate.pdf",
        )

        # Verify the enrollment was updated
        self.enrollment.refresh_from_db()
        self.assertEqual(
            self.enrollment.certificate_url,
            "/certificates/test-certificate.pdf",
        )

        # Test missing email
        data = {"certificate_path": "/certificates/test.pdf"}
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

        # Test missing certificate_path
        data = {"email": self.user.email}
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

        # Test non-existent user
        data = {
            "email": "nonexistent@example.com",
            "certificate_path": "/certificates/test.pdf",
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)

        # Test non-enrolled user
        other_user = CustomUser.objects.create(
            username="otheruser",
            email="other@example.com",
            password="password",
        )
        data = {
            "email": other_user.email,
            "certificate_path": "/certificates/test.pdf",
        }
        response = self.client.post(
            url, json.dumps(data), content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)

        # Test wrong HTTP method
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)
