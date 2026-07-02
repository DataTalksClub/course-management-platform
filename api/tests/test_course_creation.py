import json

from courses.models import Course
from api.tests.course_api_base import CourseAPITestBase


class CourseCreationAPITestCase(CourseAPITestBase):
    def test_create_course(self):
        payload = self.new_course_payload()
        body = json.dumps(payload)

        response = self.client.post(
            "/api/courses/",
            body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assert_created_course_payload(data)
        course_exists = Course.objects.filter(slug="new-course").exists()
        self.assertTrue(course_exists)

    def test_create_course_duplicate_slug(self):
        payload = {
            "slug": self.course.slug,
            "title": "Duplicate",
        }
        body = json.dumps(payload)

        response = self.client.post(
            "/api/courses/",
            body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "course_slug_exists")
