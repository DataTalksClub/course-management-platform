import yaml

from django.test import Client
from django.urls import reverse

from courses.models import Course

from .course_criteria_base import CourseCriteriaYAMLViewTestBase


class CourseCriteriaYAMLEdgeViewTestCase(CourseCriteriaYAMLViewTestBase):
    def test_course_criteria_yaml_view_no_criteria(self):
        empty_course = Course.objects.create(
            title="Empty Course",
            slug="empty-course",
        )

        url = self.course_criteria_url(empty_course)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        yaml_content = response.content.decode("utf-8")
        parsed_data = yaml.safe_load(yaml_content)
        self.assertIn("course", parsed_data)
        self.assertIn("review_criteria", parsed_data)
        self.assertEqual(len(parsed_data["review_criteria"]), 0)

    def test_course_criteria_yaml_view_nonexistent_course(self):
        url = reverse(
            "api_course_criteria_yaml",
            kwargs={"course_slug": "nonexistent-course"},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_course_criteria_yaml_view_no_auth(self):
        unauth_client = Client()

        url = self.course_criteria_url(self.course)
        response = unauth_client.get(url)

        self.assertEqual(response.status_code, 200)
        content_type = response.get("Content-Type")
        self.assertEqual(content_type, "text/plain; charset=utf-8")
