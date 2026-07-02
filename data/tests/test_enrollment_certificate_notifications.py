"""Tests for enrollment certificate notification behavior."""

from unittest.mock import patch

from .enrollment_base import (
    CertificateUpdateExpectation,
    EnrollmentDataAPIBase,
)


class EnrollmentCertificateNotificationAPITestCase(EnrollmentDataAPIBase):
    def assert_successful_certificate_notification_result(self, response):
        self.assertEqual(response.status_code, 200)
        result = response.json()
        expectation = CertificateUpdateExpectation(
            result=result,
            success=True,
            updated_count=2,
        )
        self.assert_certificate_update_result(expectation)

    def assert_certificate_notification_urls(self, second_enrollment):
        self.assert_certificate_url(
            self.enrollment, "/certificates/first.pdf"
        )
        self.assert_certificate_url(
            second_enrollment, "/certificates/second.pdf"
        )

    def assert_certificate_notification_sent(self, send_notification):
        send_notification.assert_called_once()
        notified_enrollment = send_notification.call_args.args[0]
        self.assertEqual(notified_enrollment.id, self.enrollment.id)
        self.assertEqual(
            notified_enrollment.certificate_url,
            "/certificates/first.pdf",
        )

    @patch(
        "api.views.enrollment_certificates."
        "send_certificate_availability_notification"
    )
    def test_bulk_update_enrollment_certificates_sends_new_certificate_notifications(
        self,
        send_notification,
    ):
        scenario = self.certificate_notification_scenario()

        response = self.post_certificates_with_callbacks(scenario.data)

        self.assert_successful_certificate_notification_result(response)
        self.assert_certificate_notification_urls(
            scenario.second_enrollment
        )
        self.assert_certificate_notification_sent(send_notification)
