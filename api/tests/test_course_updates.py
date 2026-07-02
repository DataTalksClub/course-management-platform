import json

from api.tests.course_api_base import CourseAPITestBase


class CourseUpdateAPITestCase(CourseAPITestBase):
    def test_patch_course(self):
        payload = self.patch_course_payload()
        body = json.dumps(payload)

        response = self.client.patch(
            "/api/courses/ml-zoomcamp/",
            body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assert_patched_course_payload(data)
        self.assert_persisted_course_patch()

    def test_patch_course_rejects_invalid_date_range(self):
        payload = {
            "start_date": "2026-05-01",
            "end_date": "2026-04-01",
        }
        body = json.dumps(payload)

        response = self.client.patch(
            "/api/courses/ml-zoomcamp/",
            body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")


class CourseUpdateValidationAPITestCase(CourseAPITestBase):
    def test_patch_course_rejects_invalid_date_format(self):
        payload = {"start_date": "01/15/2026"}
        body = json.dumps(payload)

        response = self.client.patch(
            "/api/courses/ml-zoomcamp/",
            body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_date")

    def test_patch_course_invalid_field(self):
        payload = {"slug": "changed"}
        body = json.dumps(payload)

        response = self.client.patch(
            "/api/courses/ml-zoomcamp/",
            body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_field")
