from unittest.mock import patch

from django.test import TestCase, override_settings

from course_management.datamailer.sync.status import (
    get_contact_history,
    get_contact_status,
    get_email_status,
    get_transactional_message_status,
)

from .datamailer_settings import DATAMAILER_SETTINGS


class DatamailerContactSyncStatusTest(TestCase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.contact_status"
    )
    def test_get_contact_status_uses_datamailer_client(
        self, contact_status
    ):
        contact_status.return_value = {"exists": True}

        result = get_contact_status("student@example.com")

        self.assertEqual(result, {"exists": True})
        contact_status.assert_called_once_with("student@example.com")

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.contact_history"
    )
    def test_get_contact_history_uses_datamailer_client(
        self, contact_history
    ):
        contact_history.return_value = {"transactional_messages": []}

        result = get_contact_history(42, limit=5)

        self.assertEqual(result, {"transactional_messages": []})
        contact_history.assert_called_once_with(42, limit=5)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.sync.status.get_contact_history")
    @patch("course_management.datamailer.sync.status.get_contact_status")
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

class DatamailerMessageSyncStatusTest(TestCase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_transactional.DatamailerTransactionalClient.transactional_message_status"
    )
    def test_get_transactional_message_status_uses_datamailer_client(
        self,
        message_status,
    ):
        message_status.return_value = {"message": {"id": 42}}

        result = get_transactional_message_status(42)

        self.assertEqual(result, {"message": {"id": 42}})
        message_status.assert_called_once_with(42)
