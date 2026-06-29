"""
Tests for course-related data API views.

Tests for course_criteria_yaml_view.
The old CourseContentAPITestCase has been replaced
by tests in api/tests/ for the new /api/ endpoints.
"""

import yaml

from django.test import TestCase, Client
from django.urls import reverse

from courses.models import (
    Course,
    ReviewCriteria,
    ReviewCriteriaTypes,
)

from accounts.models import CustomUser, Token


class CourseCriteriaYAMLViewTestCase(TestCase):
    """Tests for the course_criteria_yaml_view endpoint."""

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

        # Note: This endpoint doesn't require authentication
        self.client = Client()

    def create_code_quality_criteria(self):
        ReviewCriteria.objects.create(
            course=self.course,
            description="Code Quality",
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 1},
                {"criteria": "Excellent", "score": 2},
            ],
        )

    def create_features_criteria(self):
        ReviewCriteria.objects.create(
            course=self.course,
            description="Features Implemented",
            review_criteria_type=ReviewCriteriaTypes.CHECKBOXES.value,
            options=[
                {"criteria": "Basic functionality", "score": 1},
                {"criteria": "Advanced features", "score": 2},
                {"criteria": "Documentation", "score": 1},
            ],
        )

    def course_criteria_url(self, course):
        return reverse(
            "api_course_criteria_yaml",
            kwargs={"course_slug": course.slug},
        )

    def get_criteria_yaml(self, course):
        response = self.client.get(self.course_criteria_url(course))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get("Content-Type"), "text/plain; charset=utf-8"
        )
        return yaml.safe_load(response.content.decode("utf-8"))

    def assert_course_data(self, parsed_data, course):
        course_data = parsed_data["course"]
        self.assertEqual(course_data["slug"], course.slug)
        self.assertEqual(course_data["title"], course.title)

    def assert_code_quality_criteria(self, criteria):
        self.assertEqual(criteria["description"], "Code Quality")
        self.assertEqual(criteria["type"], "Radio Buttons")
        self.assertEqual(criteria["review_criteria_type"], "RB")
        self.assertEqual(len(criteria["options"]), 3)
        self.assertEqual(criteria["options"][0]["criteria"], "Poor")
        self.assertEqual(criteria["options"][0]["score"], 0)

    def assert_features_criteria(self, criteria):
        self.assertEqual(criteria["description"], "Features Implemented")
        self.assertEqual(criteria["type"], "Checkboxes")
        self.assertEqual(criteria["review_criteria_type"], "CB")
        self.assertEqual(len(criteria["options"]), 3)

    def assert_yaml_structure(self, parsed_data):
        self.assertIn("course", parsed_data)
        self.assertIn("review_criteria", parsed_data)

    def test_course_criteria_yaml_view(self):
        """Test the course criteria YAML endpoint."""
        self.create_code_quality_criteria()
        self.create_features_criteria()

        parsed_data = self.get_criteria_yaml(self.course)

        self.assert_yaml_structure(parsed_data)
        self.assert_course_data(parsed_data, self.course)
        criteria_data = parsed_data["review_criteria"]
        self.assertEqual(len(criteria_data), 2)
        self.assert_code_quality_criteria(criteria_data[0])
        self.assert_features_criteria(criteria_data[1])

    def test_course_criteria_yaml_view_no_criteria(self):
        """Test the endpoint when course has no criteria."""
        # Create a course with no criteria
        empty_course = Course.objects.create(
            title="Empty Course",
            slug="empty-course"
        )

        url = reverse(
            "api_course_criteria_yaml",
            kwargs={"course_slug": empty_course.slug}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Parse and validate YAML content
        yaml_content = response.content.decode('utf-8')
        parsed_data = yaml.safe_load(yaml_content)

        # Should have course data but empty criteria list
        self.assertIn('course', parsed_data)
        self.assertIn('review_criteria', parsed_data)
        self.assertEqual(len(parsed_data['review_criteria']), 0)

    def test_course_criteria_yaml_view_nonexistent_course(self):
        """Test the endpoint with non-existent course."""
        url = reverse(
            "api_course_criteria_yaml",
            kwargs={"course_slug": "nonexistent-course"}
        )
        response = self.client.get(url)

        # Should return 404 for non-existent course
        self.assertEqual(response.status_code, 404)

    def test_course_criteria_yaml_view_no_auth(self):
        """Test the endpoint without authentication (should work since no auth required)."""
        # Create client without authentication
        unauth_client = Client()

        url = reverse(
            "api_course_criteria_yaml",
            kwargs={"course_slug": self.course.slug}
        )
        response = unauth_client.get(url)

        # Should return 200 since no authentication is required
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get("Content-Type"), "text/plain; charset=utf-8")
