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

    def test_course_criteria_yaml_view(self):
        """Test the course criteria YAML endpoint."""
        # Create some review criteria for the test course
        criteria1 = ReviewCriteria.objects.create(
            course=self.course,
            description="Code Quality",
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
            options=[
                {"criteria": "Poor", "score": 0},
                {"criteria": "Good", "score": 1},
                {"criteria": "Excellent", "score": 2},
            ]
        )

        criteria2 = ReviewCriteria.objects.create(
            course=self.course,
            description="Features Implemented",
            review_criteria_type=ReviewCriteriaTypes.CHECKBOXES.value,
            options=[
                {"criteria": "Basic functionality", "score": 1},
                {"criteria": "Advanced features", "score": 2},
                {"criteria": "Documentation", "score": 1},
            ]
        )

        # Test the endpoint
        url = reverse(
            "api_course_criteria_yaml",
            kwargs={"course_slug": self.course.slug}
        )
        response = self.client.get(url)

        # Check response status and content type
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get("Content-Type"), "text/plain; charset=utf-8")

        # Parse and validate YAML content
        yaml_content = response.content.decode('utf-8')
        parsed_data = yaml.safe_load(yaml_content)

        # Validate structure
        self.assertIn('course', parsed_data)
        self.assertIn('review_criteria', parsed_data)

        # Validate course data
        course_data = parsed_data['course']
        self.assertEqual(course_data['slug'], self.course.slug)
        self.assertEqual(course_data['title'], self.course.title)

        # Validate criteria data
        criteria_data = parsed_data['review_criteria']
        self.assertEqual(len(criteria_data), 2)

        # Check first criteria (Code Quality)
        first_criteria = criteria_data[0]
        self.assertEqual(first_criteria['description'], 'Code Quality')
        self.assertEqual(first_criteria['type'], 'Radio Buttons')
        self.assertEqual(first_criteria['review_criteria_type'], 'RB')
        self.assertEqual(len(first_criteria['options']), 3)
        self.assertEqual(first_criteria['options'][0]['criteria'], 'Poor')
        self.assertEqual(first_criteria['options'][0]['score'], 0)

        # Check second criteria (Features Implemented)
        second_criteria = criteria_data[1]
        self.assertEqual(second_criteria['description'], 'Features Implemented')
        self.assertEqual(second_criteria['type'], 'Checkboxes')
        self.assertEqual(second_criteria['review_criteria_type'], 'CB')
        self.assertEqual(len(second_criteria['options']), 3)

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
