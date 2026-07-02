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
