import json

from django.test import Client

from .enrollment_exports_base import EnrollmentExportsAPITestBase


class EnrollmentExportAuthAPITestCase(EnrollmentExportsAPITestBase):
    def test_bulk_update_certificates_requires_token(self):
        client = Client()
        payload = {"certificates": []}
        request_body = json.dumps(payload)
        url = self.certificates_url()
        response = client.post(
            url,
            request_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"],
            "Authentication token required",
        )

    def test_course_graduates_requires_token(self):
        client = Client()
        url = self.graduates_url()
        response = client.get(url)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"],
            "Authentication token required",
        )
