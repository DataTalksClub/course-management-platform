from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings

from accounts.models import CustomUser
from course_management.datamailer import (
    DatamailerClient,
    DatamailerConfig,
    contact_payload_for_user,
    datamailer_enabled,
    send_transactional_email,
    sync_contact,
)
from courses.models import Course, Enrollment


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


class DatamailerClientTest(TestCase):
    def test_missing_env_disables_datamailer(self):
        with override_settings(
            DATAMAILER_URL="",
            DATAMAILER_API_KEY="",
            DATAMAILER_CLIENT="",
            DATAMAILER_AUDIENCE="",
        ):
            self.assertFalse(datamailer_enabled())

    def test_upsert_contact_uses_bearer_auth(self):
        session = Mock()
        response = Mock(content=b'{"ok": true}')
        response.json.return_value = {"ok": True}
        session.request.return_value = response
        config = DatamailerConfig(
            url="https://datamailer.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

        client = DatamailerClient(config, session=session)
        result = client.upsert_contact({"email": "student@example.com"})

        self.assertEqual(result, {"ok": True})
        session.request.assert_called_once_with(
            "POST",
            "https://datamailer.example.com/api/contacts",
            json={"email": "student@example.com"},
            timeout=10,
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status.assert_called_once()

    @override_settings(**DATAMAILER_SETTINGS)
    def test_contact_payload_includes_course_subscription_data(self):
        user = CustomUser.objects.create(
            email="Student@Example.com",
            username="student",
        )
        course = Course.objects.create(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            description="Machine learning",
        )

        payload = contact_payload_for_user(user, course=course)

        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(payload["client"], "dtc-courses")
        self.assertEqual(payload["audience"], "dtc-courses")
        self.assertTrue(payload["verified"])
        self.assertEqual(
            payload["email_validation"]["status"],
            "externally_validated",
        )
        self.assertEqual(payload["tags"], ["course-ml-zoomcamp"])
        self.assertEqual(payload["custom_fields"]["course_slug"], "ml-zoomcamp")

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.DatamailerClient.upsert_contact")
    def test_sync_contact_logs_and_continues_on_api_failure(self, upsert):
        upsert.side_effect = requests.RequestException("network error")
        user = CustomUser.objects.create(email="student@example.com")

        sync_contact(user)

        upsert.assert_called_once()

    @override_settings(**DATAMAILER_SETTINGS, DATAMAILER_STRICT=True)
    @patch("course_management.datamailer.DatamailerClient.upsert_contact")
    def test_sync_contact_can_be_strict(self, upsert):
        upsert.side_effect = requests.RequestException("network error")
        user = CustomUser.objects.create(email="student@example.com")

        with self.assertRaises(requests.RequestException):
            sync_contact(user)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.DatamailerClient.send_transactional")
    def test_send_transactional_email_uses_datamailer_client(self, send):
        send.return_value = {"id": "message-id"}

        result = send_transactional_email(
            {
                "template": "welcome",
                "to": "student@example.com",
            }
        )

        self.assertEqual(result, {"id": "message-id"})
        send.assert_called_once_with(
            {
                "template": "welcome",
                "to": "student@example.com",
            }
        )


class DatamailerSignalTest(TestCase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.signals.sync_contact")
    def test_new_user_syncs_after_commit(self, sync):
        with self.captureOnCommitCallbacks(execute=True):
            user = CustomUser.objects.create(email="student@example.com")

        sync.assert_called_once_with(user)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("courses.signals.sync_contact")
    def test_new_enrollment_syncs_after_commit(self, sync):
        user = CustomUser.objects.create(email="student@example.com")
        course = Course.objects.create(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            description="Machine learning",
        )
        sync.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            enrollment = Enrollment.objects.create(
                student=user,
                course=course,
            )

        sync.assert_called_once_with(
            enrollment.student,
            course=enrollment.course,
        )
