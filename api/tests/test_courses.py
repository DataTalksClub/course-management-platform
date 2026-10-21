from django.test import Client

from api.tests.course_api_base import CourseAPITestBase


class CoursesListAPITestCase(CourseAPITestBase):
    def test_list_courses(self):
        response = self.client.get("/api/courses/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        courses_by_slug = {
            course["slug"]: course for course in data["courses"]
        }
        self.assertIn("ml-zoomcamp", courses_by_slug)
        self.assertEqual(
            courses_by_slug["ml-zoomcamp"]["start_date"], "2026-01-15"
        )
        self.assertEqual(
            courses_by_slug["ml-zoomcamp"]["end_date"], "2026-04-15"
        )
        self.assertEqual(
            courses_by_slug["ml-zoomcamp"]["registration_url"],
            "https://courses.datatalks.club/ml/register",
        )
        self.assertEqual(
            courses_by_slug["ml-zoomcamp"]["github_repo_url"],
            "https://github.com/DataTalksClub/ml-zoomcamp",
        )

    def test_list_courses_requires_auth(self):
        client = Client()
        response = client.get("/api/courses/")
        self.assertEqual(response.status_code, 401)
