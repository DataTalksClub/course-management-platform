from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings

from accounts.models import CustomUser
from course_management.datamailer import (
    DatamailerClient,
    DatamailerConfig,
    contact_tags_for_course,
    contact_payload_for_user,
    datamailer_enabled,
    get_contact_history,
    get_contact_status,
    get_email_status,
    get_transactional_message_status,
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

    def test_contact_status_uses_configured_scope(self):
        session = Mock()
        response = Mock(content=b'{"exists": true}')
        response.json.return_value = {"exists": True}
        session.request.return_value = response
        config = DatamailerConfig(
            url="https://datamailer.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

        client = DatamailerClient(config, session=session)
        result = client.contact_status("student@example.com")

        self.assertEqual(result, {"exists": True})
        session.request.assert_called_once_with(
            "GET",
            "https://datamailer.example.com/api/contacts/status",
            json=None,
            params={
                "email": "student@example.com",
                "audience": "dtc-courses",
                "client": "dtc-courses",
            },
            timeout=10,
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status.assert_called_once()

    def test_contact_history_uses_configured_scope(self):
        session = Mock()
        response = Mock(content=b'{"transactional_messages": []}')
        response.json.return_value = {"transactional_messages": []}
        session.request.return_value = response
        config = DatamailerConfig(
            url="https://datamailer.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

        client = DatamailerClient(config, session=session)
        result = client.contact_history(42, limit=5)

        self.assertEqual(result, {"transactional_messages": []})
        session.request.assert_called_once_with(
            "GET",
            "https://datamailer.example.com/api/contacts/42/history",
            json=None,
            params={
                "audience": "dtc-courses",
                "client": "dtc-courses",
                "limit": 5,
            },
            timeout=10,
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status.assert_called_once()

    def test_transactional_message_status_uses_message_id(self):
        session = Mock()
        response = Mock(content=b'{"message": {"id": 42}}')
        response.json.return_value = {"message": {"id": 42}}
        session.request.return_value = response
        config = DatamailerConfig(
            url="https://datamailer.example.com",
            api_key="secret-token",
            client="dtc-courses",
            audience="dtc-courses",
        )

        client = DatamailerClient(config, session=session)
        result = client.transactional_message_status(42)

        self.assertEqual(result, {"message": {"id": 42}})
        session.request.assert_called_once_with(
            "GET",
            "https://datamailer.example.com/api/transactional/messages/42",
            json=None,
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
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
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
        self.assertEqual(
            payload["tags"],
            [
                "course-ml-zoomcamp",
                "course-cohort-ml-zoomcamp-2026",
            ],
        )
        self.assertEqual(
            payload["custom_fields"]["course_slug"],
            "ml-zoomcamp-2026",
        )
        self.assertEqual(
            payload["custom_fields"]["course_family_slug"],
            "ml-zoomcamp",
        )
        self.assertEqual(
            payload["custom_fields"]["course_cohort_slug"],
            "ml-zoomcamp-2026",
        )

    def test_contact_tags_for_course_without_trailing_year(self):
        course = Course(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            description="Machine learning",
        )

        self.assertEqual(
            contact_tags_for_course(course),
            [
                "course-ml-zoomcamp",
                "course-cohort-ml-zoomcamp",
            ],
        )

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
                "template_key": "welcome",
                "email": "student@example.com",
            }
        )

        self.assertEqual(result, {"id": "message-id"})
        send.assert_called_once_with(
            {
                "template_key": "welcome",
                "email": "student@example.com",
            }
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
    )
    @patch("course_management.datamailer.DatamailerClient.send_transactional")
    def test_send_transactional_email_adds_configured_from_email(self, send):
        send.return_value = {"id": "message-id"}

        send_transactional_email(
            {
                "template_key": "welcome",
                "email": "student@example.com",
            }
        )

        send.assert_called_once_with(
            {
                "template_key": "welcome",
                "email": "student@example.com",
                "from_email": "courses",
            }
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
    )
    @patch("course_management.datamailer.DatamailerClient.send_transactional")
    def test_send_transactional_email_keeps_explicit_from_email(self, send):
        send.return_value = {"id": "message-id"}

        send_transactional_email(
            {
                "template_key": "welcome",
                "email": "student@example.com",
                "from_email": "no-reply",
            }
        )

        send.assert_called_once_with(
            {
                "template_key": "welcome",
                "email": "student@example.com",
                "from_email": "no-reply",
            }
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.DatamailerClient.contact_status")
    def test_get_contact_status_uses_datamailer_client(self, contact_status):
        contact_status.return_value = {"exists": True}

        result = get_contact_status("student@example.com")

        self.assertEqual(result, {"exists": True})
        contact_status.assert_called_once_with("student@example.com")

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.DatamailerClient.contact_history")
    def test_get_contact_history_uses_datamailer_client(self, contact_history):
        contact_history.return_value = {"transactional_messages": []}

        result = get_contact_history(42, limit=5)

        self.assertEqual(result, {"transactional_messages": []})
        contact_history.assert_called_once_with(42, limit=5)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.get_contact_history")
    @patch("course_management.datamailer.get_contact_status")
    def test_get_email_status_combines_status_and_history(
        self,
        contact_status,
        contact_history,
    ):
        contact_status.return_value = {
            "contact_id": 42,
            "email": "student@example.com",
        }
        contact_history.return_value = {"transactional_messages": []}

        result = get_email_status("student@example.com", limit=5)

        self.assertEqual(
            result,
            {
                "status": {
                    "contact_id": 42,
                    "email": "student@example.com",
                },
                "history": {"transactional_messages": []},
            },
        )
        contact_status.assert_called_once_with("student@example.com")
        contact_history.assert_called_once_with(42, limit=5)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.DatamailerClient.transactional_message_status")
    def test_get_transactional_message_status_uses_datamailer_client(
        self,
        message_status,
    ):
        message_status.return_value = {"message": {"id": 42}}

        result = get_transactional_message_status(42)

        self.assertEqual(result, {"message": {"id": 42}})
        message_status.assert_called_once_with(42)


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
