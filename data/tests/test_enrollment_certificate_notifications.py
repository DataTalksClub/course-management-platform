"""Tests for enrollment certificate notification behavior.

Certificate upload and certificate notification are separate endpoints
(``api_course_certificates`` and ``api_course_certificate_notify``). Upload
persists certificate URLs only, and never calls Datamailer: a course with a
large graduating class used to send one synchronous Datamailer call per
enrollment from inside the upload request, which could run past gunicorn's
worker timeout and turn into a 500 (see cmp-prod-alb-target-5xx). Splitting
the notification into its own single-enrollment endpoint means an upload
request can never fan out into more than zero Datamailer calls.
"""

from unittest.mock import patch

from .enrollment_base import (
    CertificateUpdateExpectation,
    EnrollmentDataAPIBase,
)


class EnrollmentCertificateUploadDoesNotNotifyAPITestCase(
    EnrollmentDataAPIBase
):
    @patch(
        "api.views.enrollment_certificates."
        "send_certificate_availability_notification"
    )
    def test_bulk_update_enrollment_certificates_never_sends_notifications(
        self,
        send_notification,
    ):
        scenario = self.certificate_notification_scenario()

        response = self.post_certificates_with_callbacks(scenario.data)

        self.assertEqual(response.status_code, 200)
        result = response.json()
        expectation = CertificateUpdateExpectation(
            result=result,
            success=True,
            updated_count=2,
        )
        self.assert_certificate_update_result(expectation)
        self.assert_certificate_url(
            self.enrollment, "/certificates/first.pdf"
        )
        self.assert_certificate_url(
            scenario.second_enrollment, "/certificates/second.pdf"
        )
        send_notification.assert_not_called()

    def test_bulk_update_response_flags_first_time_certificates(self):
        scenario = self.certificate_notification_scenario()

        response = self.post_certificates(scenario.data)

        result = response.json()
        updates_by_email = {}
        for update in result["updated"]:
            updates_by_email[update["email"]] = update

        self.assertTrue(updates_by_email[self.user.email]["notify"])
        self.assertFalse(
            updates_by_email[
                scenario.second_enrollment.student.email
            ]["notify"]
        )


class EnrollmentCertificateNotifyAPITestCase(EnrollmentDataAPIBase):
    @patch(
        "api.views.enrollment_certificates."
        "send_certificate_availability_notification"
    )
    def test_notify_sends_notification_for_existing_certificate(
        self,
        send_notification,
    ):
        self.enrollment.certificate_url = "/certificates/first.pdf"
        self.enrollment.save()

        response = self.post_certificate_notify(self.user.email)

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])
        self.assertEqual(result["email"], self.user.email)
        self.assertEqual(
            result["certificate_url"], "/certificates/first.pdf"
        )
        send_notification.assert_called_once()
        notified_enrollment = send_notification.call_args.args[0]
        self.assertEqual(notified_enrollment.id, self.enrollment.id)

    def test_notify_requires_email(self):
        response = self.client.post(
            self.certificate_notify_url(),
            "{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_notify_unknown_user_returns_error(self):
        response = self.post_certificate_notify("missing@example.com")

        result = response.json()
        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "user_not_found")

    def test_notify_user_not_enrolled_returns_error(self):
        other_user = self.create_other_user()

        response = self.post_certificate_notify(other_user.email)

        result = response.json()
        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "not_enrolled")

    def test_notify_without_certificate_returns_error(self):
        response = self.post_certificate_notify(self.user.email)

        result = response.json()
        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "certificate_missing")

    def test_notify_rejects_get(self):
        response = self.client.get(self.certificate_notify_url())

        self.assertEqual(response.status_code, 405)
