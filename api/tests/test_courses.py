from django.test import Client

from api.tests.course_api_base import CourseAPITestBase


class CoursesListAPITestCase(CourseAPITestBase):
    def test_list_courses(self):
        response = self.client.get("/api/courses/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        courses_count = len(data["courses"])
        self.assertEqual(courses_count, 1)
        self.assertEqual(data["courses"][0]["slug"], "ml-zoomcamp")
        self.assertEqual(data["courses"][0]["start_date"], "2026-01-15")
        self.assertEqual(data["courses"][0]["end_date"], "2026-04-15")
        self.assertEqual(
            data["courses"][0]["registration_url"],
            "https://courses.datatalks.club/ml/register",
        )
        self.assertEqual(
            data["courses"][0]["github_repo_url"],
            "https://github.com/DataTalksClub/ml-zoomcamp",
        )

    def test_list_courses_requires_auth(self):
        client = Client()
        response = client.get("/api/courses/")
        self.assertEqual(response.status_code, 401)
