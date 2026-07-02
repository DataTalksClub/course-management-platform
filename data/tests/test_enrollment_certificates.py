"""Tests for enrollment certificate update API views."""

from .enrollment_base import (
    CertificateUpdateExpectation,
    EnrollmentDataAPIBase,
)


class EnrollmentCertificateBulkUpdateAssertionMixin:
    def assert_bulk_certificate_error_codes(self, result):
        error_codes = set()
        for error in result["errors"]:
            error_codes.add(error["code"])
        self.assertEqual(
            error_codes,
            {"missing_fields", "not_enrolled", "user_not_found"},
        )

    def assert_mixed_certificate_urls(self, second_enrollment):
        self.assert_certificate_url(
            self.enrollment, "/certificates/first.pdf"
        )
        self.assert_certificate_url(
            second_enrollment, "/certificates/second.pdf"
        )

    def assert_certificates_reject_get(self):
        url = self.certificate_url()

        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)


class EnrollmentCertificateMixedBulkUpdateAPITestCase(
    EnrollmentCertificateBulkUpdateAssertionMixin,
    EnrollmentDataAPIBase,
):
    def test_bulk_update_enrollment_certificates_view(self):
        second_user, second_enrollment = self.create_enrolled_user(
            "seconduser", "second@example.com"
        )
        other_user = self.create_other_user()
        data = self.mixed_certificate_payload(second_user, other_user)

        response = self.post_certificates(data)

        self.assertEqual(response.status_code, 200)
        result = response.json()
        expectation = CertificateUpdateExpectation(
            result=result,
            success=False,
            updated_count=2,
            error_count=3,
        )
        self.assert_certificate_update_result(expectation)
        self.assert_bulk_certificate_error_codes(result)
        self.assert_mixed_certificate_urls(second_enrollment)
        self.assert_certificates_reject_get()


class EnrollmentCertificateArrayPayloadAPITestCase(EnrollmentDataAPIBase):
    def test_bulk_update_enrollment_certificates_accepts_array_payload(
        self,
    ):
        data = [
            {
                "email": self.user.email,
                "certificate_path": "/certificates/array.pdf",
            }
        ]

        response = self.post_certificates(data)

        self.assertEqual(response.status_code, 200)
        result = response.json()
        expectation = CertificateUpdateExpectation(
            result=result,
            success=True,
            updated_count=1,
            error_count=0,
        )
        self.assert_certificate_update_result(expectation)
        self.assert_certificate_url(
            self.enrollment, "/certificates/array.pdf"
        )
