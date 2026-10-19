import json
from unittest.mock import patch

from accounts.models import CustomUser, Token

from .enrollment_exports_base import EnrollmentExportsAPITestBase


class EnrollmentExportSuccessAPITestCase(EnrollmentExportsAPITestBase):
    def single_certificate_payload(self):
        certificate = self.certificate_item(
            "student@example.com",
            "/certificates/student.pdf",
        )
        certificates = []
        certificates.append(certificate)
        return {"certificates": certificates}

    def assert_single_certificate_response(self, response, enrollment):
        self.assertEqual(response.status_code, 200)
        updated_item = {
            "index": 0,
            "email": "student@example.com",
            "enrollment_id": enrollment.id,
            "certificate_url": "/certificates/student.pdf",
            "notify": True,
        }
        updated = []
        updated.append(updated_item)
        expected_response = {
            "success": True,
            "updated_count": 1,
            "error_count": 0,
            "updated": updated,
            "errors": [],
        }
        response_data = response.json()
        self.assertEqual(response_data, expected_response)

    def test_bulk_update_certificates_updates_enrollment_without_notifying(
        self,
    ):
        enrollment = self.create_enrollment("student@example.com")

        with patch(
            "api.views.enrollment_certificates."
            "send_certificate_availability_notification"
        ) as send_notification:
            with self.captureOnCommitCallbacks(execute=True):
                payload = self.single_certificate_payload()
                response = self.post_certificates(payload)

        self.assert_single_certificate_response(response, enrollment)
        self.assert_certificate_url(enrollment, "/certificates/student.pdf")
        send_notification.assert_not_called()


class CertificateBulkUpdateStaffAuthTestCase(EnrollmentExportsAPITestBase):
    def single_certificate_payload(self):
        certificate = self.certificate_item(
            "student@example.com",
            "/certificates/student.pdf",
        )
        certificates = []
        certificates.append(certificate)
        return {"certificates": certificates}

    def student_token_headers(self):
        student = CustomUser.objects.create(
            username="student-token",
            email="student-token@example.com",
        )
        token = Token.objects.create(user=student)
        return {"HTTP_AUTHORIZATION": f"Token {token.key}"}

    def test_non_staff_token_cannot_update_certificates(self):
        enrollment = self.create_enrollment("student@example.com")
        headers = self.student_token_headers()

        with patch(
            "api.views.enrollment_certificates."
            "send_certificate_availability_notification"
        ) as send_notification:
            payload = self.single_certificate_payload()
            response = self.client.post(
                self.certificates_url(),
                json.dumps(payload),
                content_type="application/json",
                **headers,
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "error": "Staff token required",
                "code": "staff_token_required",
            },
        )
        self.assert_certificate_url(enrollment, "")
        send_notification.assert_not_called()


class CourseGraduatesStaffAuthTestCase(EnrollmentExportsAPITestBase):
    def student_token_headers(self):
        student = CustomUser.objects.create(
            username="student-token",
            email="student-token@example.com",
        )
        token = Token.objects.create(user=student)
        return {"HTTP_AUTHORIZATION": f"Token {token.key}"}

    def test_non_staff_token_cannot_export_course_graduates(self):
        self.create_enrollment("student@example.com")
        headers = self.student_token_headers()

        response = self.client.get(
            self.graduates_url(),
            **headers,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "error": "Staff token required",
                "code": "staff_token_required",
            },
        )
        self.assertNotIn("graduates", response.json())
