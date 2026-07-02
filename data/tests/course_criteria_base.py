import yaml

from django.test import Client, TestCase
from django.urls import reverse

from courses.models import (
    Course,
    ReviewCriteria,
    ReviewCriteriaTypes,
)


class CourseCriteriaYAMLTestBase(TestCase):
    def setUp(self):
        self.client = Client()
        self.course = Course.objects.create(
            title="Test Course", slug="test-course"
        )

    def create_code_quality_criteria(self):
        poor_option = {"criteria": "Poor", "score": 0}
        good_option = {"criteria": "Good", "score": 1}
        excellent_option = {"criteria": "Excellent", "score": 2}
        options = []
        options.append(poor_option)
        options.append(good_option)
        options.append(excellent_option)
        ReviewCriteria.objects.create(
            course=self.course,
            description="Code Quality",
            review_criteria_type=ReviewCriteriaTypes.RADIO_BUTTONS.value,
            options=options,
        )

    def create_features_criteria(self):
        basic_option = {"criteria": "Basic functionality", "score": 1}
        advanced_option = {"criteria": "Advanced features", "score": 2}
        documentation_option = {"criteria": "Documentation", "score": 1}
        options = []
        options.append(basic_option)
        options.append(advanced_option)
        options.append(documentation_option)
        ReviewCriteria.objects.create(
            course=self.course,
            description="Features Implemented",
            review_criteria_type=ReviewCriteriaTypes.CHECKBOXES.value,
            options=options,
        )

    def course_criteria_url(self, course):
        return reverse(
            "api_course_criteria_yaml",
            kwargs={"course_slug": course.slug},
        )

    def get_criteria_yaml(self, course):
        criteria_url = self.course_criteria_url(course)
        response = self.client.get(criteria_url)
        self.assertEqual(response.status_code, 200)
        content_type = response.get("Content-Type")
        self.assertEqual(content_type, "text/plain; charset=utf-8")
        content = response.content.decode("utf-8")
        return yaml.safe_load(content)


class CourseCriteriaYAMLAssertionMixin:
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


class CourseCriteriaYAMLViewTestBase(
    CourseCriteriaYAMLAssertionMixin,
    CourseCriteriaYAMLTestBase,
):
    """Shared base for course criteria YAML endpoint tests."""
