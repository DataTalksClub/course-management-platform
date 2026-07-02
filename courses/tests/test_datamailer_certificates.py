from unittest.mock import patch

from django.test import TestCase, override_settings

from accounts.models import CustomUser
from course_management.datamailer.keys import course_graduates_list_key
from course_management.datamailer.payloads.certificate_availability import (
    certificate_availability_notification_payload,
)
from course_management.datamailer.payloads.course_graduates import (
    course_graduate_recipient_list_payload,
)
from course_management.datamailer.sync.certificates import (
    send_certificate_availability_notification,
)
from courses.models import Course, Enrollment


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


class DatamailerCertificateFixtureMixin:
    def create_ml_course(self):
        return Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )

    def create_enrollment(self, user, course, **overrides):
        defaults = {"student": user, "course": course}
        defaults.update(overrides)
        return Enrollment.objects.create(**defaults)

    def create_certificate_enrollment(self):
        user = CustomUser.objects.create(
            email="student@example.com",
            username="student",
        )
        course = self.create_ml_course()
        return self.create_enrollment(
            user,
            course,
            certificate_url="/certificates/student.pdf",
        )

    def create_graduate_enrollment(self):
        user = CustomUser.objects.create(
            email="student@example.com",
            username="student",
        )
        course = self.create_ml_course()
        return self.create_enrollment(
            user,
            course,
            total_score=91,
            certificate_url="/certificates/student.pdf",
        )


class CertificateAvailabilityAssertionMixin:
    def assert_certificate_availability_identity(self, payload, enrollment):
        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(payload["audience"], "dtc-courses")
        self.assertEqual(payload["client"], "dtc-courses")
        self.assertEqual(
            payload["template_key"],
            "certificate-availability-notification",
        )
        self.assertEqual(
            payload["idempotency_key"],
            f"certificate-available:{enrollment.pk}",
        )
        self.assertEqual(payload["from_email"], "courses")

    def assert_certificate_availability_context(self, payload):
        self.assertEqual(
            payload["context"]["certificate_url"],
            "https://courses.example.com/certificates/student.pdf",
        )
        self.assertEqual(
            payload["context"]["course_url"],
            "https://courses.example.com/ml-zoomcamp-2026/",
        )

    def assert_certificate_availability_metadata(self, payload):
        self.assertEqual(
            payload["metadata"]["event"],
            "certificate_availability",
        )
        self.assertEqual(payload["category_tag"], "course-updates")
        self.assertEqual(
            payload["metadata"]["preference_key"],
            "email_course_updates",
        )

    def assert_certificate_availability_copy(self, payload):
        self.assertIn(
            "Congratulations",
            payload["context"]["intro_text"],
        )
        self.assertEqual(
            payload["context"]["notification_category"],
            "course-related emails",
        )

    def assert_certificate_availability_payload(self, payload, enrollment):
        self.assert_certificate_availability_identity(payload, enrollment)
        self.assert_certificate_availability_context(payload)
        self.assert_certificate_availability_metadata(payload)
        self.assert_certificate_availability_copy(payload)


class CourseGraduateRecipientAssertionMixin:
    def assert_course_graduate_recipient_payload(
        self,
        list_key,
        payload,
        enrollment,
    ):
        expected_list_key = course_graduates_list_key(enrollment.course)
        self.assertEqual(list_key, expected_list_key)
        self.assertEqual(payload["list"]["type"], "custom")
        self.assertEqual(
            payload["list"]["metadata"]["outcome"],
            "course_graduated",
        )
        self.assertEqual(len(payload["members"]), 1)
        member = payload["members"][0]
        self.assertEqual(member["email"], "student@example.com")
        self.assertEqual(
            member["source_object_key"], f"enrollment:{enrollment.pk}"
        )
        self.assertEqual(member["metadata"]["outcome"], "course_graduated")
        self.assertEqual(member["metadata"]["total_score"], 91)
        self.assertEqual(
            member["metadata"]["certificate_url"],
            "https://courses.example.com/certificates/student.pdf",
        )


class DatamailerCertificatePayloadTestCase(
    DatamailerCertificateFixtureMixin,
    CertificateAvailabilityAssertionMixin,
    CourseGraduateRecipientAssertionMixin,
    TestCase,
):
    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_certificate_availability_notification_payload(self):
        enrollment = self.create_certificate_enrollment()

        payload = certificate_availability_notification_payload(
            enrollment
        )

        self.assert_certificate_availability_payload(payload, enrollment)

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_course_graduate_recipient_list_payload_targets_graduated_outcome(
        self,
    ):
        enrollment = self.create_graduate_enrollment()

        list_key, payload = course_graduate_recipient_list_payload(
            enrollment
        )

        self.assert_course_graduate_recipient_payload(
            list_key,
            payload,
            enrollment,
        )


class DatamailerCertificateSendTestCase(
    DatamailerCertificateFixtureMixin,
    TestCase,
):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_transactional.DatamailerTransactionalClient.send_transactional"
    )
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListClient.bulk_upsert_recipient_list_members"
    )
    def test_certificate_availability_notification_uses_datamailer_preference_category(
        self,
        bulk_upsert,
        send,
    ):
        bulk_upsert.return_value = {"updated_count": 1}
        send.return_value = {"id": 123}
        enrollment = self.create_certificate_enrollment()

        payload = certificate_availability_notification_payload(
            enrollment
        )
        result = send_certificate_availability_notification(enrollment)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["category_tag"], "course-updates")
        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(result, {"id": 123})
        bulk_upsert.assert_called_once()
        send.assert_called_once()

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_transactional.DatamailerTransactionalClient.send_transactional"
    )
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListClient.bulk_upsert_recipient_list_members"
    )
    def test_send_certificate_availability_notification_uses_transactional_send(
        self,
        bulk_upsert,
        send,
    ):
        bulk_upsert.return_value = {"updated_count": 1}
        send.return_value = {"id": 123}
        enrollment = self.create_certificate_enrollment()

        result = send_certificate_availability_notification(enrollment)

        self.assertEqual(result, {"id": 123})
        bulk_upsert.assert_called_once()
        expected_list_key = course_graduates_list_key(enrollment.course)
        self.assertEqual(
            bulk_upsert.call_args.args[0],
            expected_list_key,
        )
        send.assert_called_once()
        payload = send.call_args.args[0]
        self.assertEqual(
            payload["template_key"],
            "certificate-availability-notification",
        )
