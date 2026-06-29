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

    def test_bulk_update_certificates_updates_enrollment_and_notifies(self):
        enrollment = self.create_enrollment("student@example.com")
        payload = {
            "certificates": [
                {
                    "email": "student@example.com",
                    "certificate_path": "/certificates/student.pdf",
                }
            ]
        }

        with patch(
            "api.views.enrollment_exports."
            "send_certificate_availability_notification"
        ) as send_notification:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.post_certificates(payload)

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
        enrollment.refresh_from_db()
        self.assertEqual(
            enrollment.certificate_url,
            "/certificates/student.pdf",
        )
        send_notification.assert_called_once_with(enrollment)

    def test_bulk_update_certificates_reports_mixed_item_errors(self):
        enrolled = self.create_enrollment("enrolled@example.com")
        self.create_student("not-enrolled@example.com")

        response = self.post_certificates(
            [
                {
                    "email": "enrolled@example.com",
                    "certificate_path": "/certificates/enrolled.pdf",
                },
                {
                    "email": "not-enrolled@example.com",
                    "certificate_path": "/certificates/not-enrolled.pdf",
                },
                {
                    "email": "missing-user@example.com",
                    "certificate_path": "/certificates/missing.pdf",
                },
                {"email": "missing-path@example.com"},
                "not an object",
            ]
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["updated_count"], 1)
        self.assertEqual(data["error_count"], 4)
        self.assertEqual(data["updated"][0]["enrollment_id"], enrolled.id)
        self.assertEqual(
            [error["code"] for error in data["errors"]],
            [
                "missing_fields",
                "invalid_item",
                "not_enrolled",
                "user_not_found",
            ],
        )

        enrolled.refresh_from_db()
        self.assertEqual(
            enrolled.certificate_url,
            "/certificates/enrolled.pdf",
        )

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
