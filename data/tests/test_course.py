"""
Tests for course-related data API views.

Tests for course_criteria_yaml_view.
The old CourseContentAPITestCase has been replaced
by tests in api/tests/ for the new /api/ endpoints.
"""

from .course_criteria_base import CourseCriteriaYAMLViewTestBase


class CourseCriteriaYAMLViewTestCase(CourseCriteriaYAMLViewTestBase):
    """Tests for the course_criteria_yaml_view endpoint."""

    def test_course_criteria_yaml_view(self):
        self.create_code_quality_criteria()
        self.create_features_criteria()

        parsed_data = self.get_criteria_yaml(self.course)

        self.assert_yaml_structure(parsed_data)
        self.assert_course_data(parsed_data, self.course)
        criteria_data = parsed_data["review_criteria"]
        self.assertEqual(len(criteria_data), 2)
        self.assert_code_quality_criteria(criteria_data[0])
        self.assert_features_criteria(criteria_data[1])
