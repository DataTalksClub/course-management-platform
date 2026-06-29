import json
from unittest.mock import patch

from django.test import Client, TestCase

from accounts.models import CustomUser, Token
from courses.models import Course, Enrollment


class EnrollmentExportsAPITestCase(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create(
            username="staff",
            email="staff@example.com",
            is_staff=True,
        )
        self.token = Token.objects.create(user=self.staff)
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Token {self.token.key}"
        )
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            description="Test",
        )

    def post_certificates(self, payload):
        return self.client.post(
            f"/api/courses/{self.course.slug}/certificates",
            json.dumps(payload),
            content_type="application/json",
        )

    def create_student(self, email):
        return CustomUser.objects.create(username=email, email=email)

    def create_enrollment(self, email, certificate_url=""):
        student = self.create_student(email)
        return Enrollment.objects.create(
            student=student,
            course=self.course,
            certificate_url=certificate_url,
        )

    def certificate_item(self, email, path):
        return {
            "email": email,
            "certificate_path": path,
        }

    def single_certificate_payload(self):
        return {
            "certificates": [
                self.certificate_item(
                    "student@example.com",
                    "/certificates/student.pdf",
                )
            ]
        }

    def mixed_certificate_payload(self):
        return [
            self.certificate_item(
                "enrolled@example.com",
                "/certificates/enrolled.pdf",
            ),
            self.certificate_item(
                "not-enrolled@example.com",
                "/certificates/not-enrolled.pdf",
            ),
            self.certificate_item(
                "missing-user@example.com",
                "/certificates/missing.pdf",
            ),
            {"email": "missing-path@example.com"},
            "not an object",
        ]

    def assert_certificate_url(self, enrollment, expected_url):
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.certificate_url, expected_url)

    def assert_single_certificate_response(self, response, enrollment):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "success": True,
                "updated_count": 1,
                "error_count": 0,
                "updated": [
                    {
                        "index": 0,
                        "email": "student@example.com",
                        "enrollment_id": enrollment.id,
                        "certificate_url": "/certificates/student.pdf",
                    }
                ],
                "errors": [],
            },
        )

    def assert_mixed_certificate_response(self, response, enrolled):
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["updated_count"], 1)
        self.assertEqual(data["error_count"], 4)
        self.assertEqual(data["updated"][0]["enrollment_id"], enrolled.id)
        error_codes = []
        for error in data["errors"]:
            error_codes.append(error["code"])
        self.assertEqual(
            error_codes,
            [
                "missing_fields",
                "invalid_item",
                "not_enrolled",
                "user_not_found",
            ],
        )

    def test_bulk_update_certificates_updates_enrollment_and_notifies(self):
        enrollment = self.create_enrollment("student@example.com")

        with patch(
            "api.views.enrollment_exports."
            "send_certificate_availability_notification"
        ) as send_notification:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.post_certificates(
                    self.single_certificate_payload()
                )

        self.assert_single_certificate_response(response, enrollment)
        self.assert_certificate_url(enrollment, "/certificates/student.pdf")
        send_notification.assert_called_once_with(enrollment)

    def test_bulk_update_certificates_reports_mixed_item_errors(self):
        enrolled = self.create_enrollment("enrolled@example.com")
        self.create_student("not-enrolled@example.com")

        response = self.post_certificates(self.mixed_certificate_payload())

        self.assert_mixed_certificate_response(response, enrolled)
        self.assert_certificate_url(enrolled, "/certificates/enrolled.pdf")

    def test_bulk_update_certificates_requires_token(self):
        client = Client()
        response = client.post(
            f"/api/courses/{self.course.slug}/certificates",
            json.dumps({"certificates": []}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"],
            "Authentication token required",
        )
