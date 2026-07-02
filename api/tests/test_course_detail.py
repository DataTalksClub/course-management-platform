from api.tests.course_api_base import CourseAPITestBase


class CourseDetailAPITestCase(CourseAPITestBase):
    def test_course_detail(self):
        self.create_course_detail_fixture()

        response = self.client.get("/api/courses/ml-zoomcamp/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assert_course_detail_payload(data)

    def test_course_detail_not_found(self):
        response = self.client.get("/api/courses/nonexistent/")
        self.assertEqual(response.status_code, 404)
