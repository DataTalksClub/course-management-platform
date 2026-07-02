from unittest.mock import patch

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

    def test_bulk_update_certificates_updates_enrollment_and_notifies(self):
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
        send_notification.assert_called_once_with(enrollment)
