"""
Tests for course-related data API views.

Tests for course_criteria_yaml_view.
The old CourseContentAPITestCase has been replaced
by tests in api/tests/ for the new /api/ endpoints.
"""

from .course_criteria_base import CourseCriteriaYAMLTestBase


def assert_course_data(test_case, parsed_data, course):
    course_data = parsed_data["course"]
    test_case.assertEqual(course_data["slug"], course.slug)
    test_case.assertEqual(course_data["title"], course.title)


def assert_code_quality_criteria(test_case, criteria):
    test_case.assertEqual(criteria["description"], "Code Quality")
    test_case.assertEqual(criteria["type"], "Radio Buttons")
    test_case.assertEqual(criteria["review_criteria_type"], "RB")
    options_count = len(criteria["options"])
    test_case.assertEqual(options_count, 3)
    test_case.assertEqual(criteria["options"][0]["criteria"], "Poor")
    test_case.assertEqual(criteria["options"][0]["score"], 0)


def assert_features_criteria(test_case, criteria):
    test_case.assertEqual(criteria["description"], "Features Implemented")
    test_case.assertEqual(criteria["type"], "Checkboxes")
    test_case.assertEqual(criteria["review_criteria_type"], "CB")
    options_count = len(criteria["options"])
    test_case.assertEqual(options_count, 3)


def assert_yaml_structure(test_case, parsed_data):
    test_case.assertIn("course", parsed_data)
    test_case.assertIn("review_criteria", parsed_data)


class CourseCriteriaYAMLViewTestCase(CourseCriteriaYAMLTestBase):
    """Tests for the course_criteria_yaml_view endpoint."""

    def test_course_criteria_yaml_view(self):
        self.create_code_quality_criteria()
        self.create_features_criteria()

        parsed_data = self.get_criteria_yaml(self.course)

        assert_yaml_structure(self, parsed_data)
        assert_course_data(self, parsed_data, self.course)
        criteria_data = parsed_data["review_criteria"]
        criteria_count = len(criteria_data)
        self.assertEqual(criteria_count, 2)
        assert_code_quality_criteria(self, criteria_data[0])
        assert_features_criteria(self, criteria_data[1])
