from unittest.mock import patch

import requests
from django.test import override_settings

from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)
from course_management.datamailer.sync.transactional import (
    send_transactional_email,
)
from courses.tests.datamailer_contact_base import (
    DATAMAILER_SETTINGS,
    DatamailerContactBase,
)


class DatamailerTransactionalTest(DatamailerContactBase):
    @override_settings(**DATAMAILER_SETTINGS, DATAMAILER_FROM_EMAIL="")
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transactional"
    )
    def test_send_transactional_email_uses_datamailer_client(
        self, send
    ):
        self.configure_transactional_send_success(send)

        payload = self.transactional_email_payload()
        result = send_transactional_email(payload)

        self.assertEqual(result["message"]["id"], "message-id")
        self.assert_transactional_send_called(send)
        self.assert_transactional_send_audit()

    @override_settings(**DATAMAILER_SETTINGS, DATAMAILER_FROM_EMAIL="")
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transactional"
    )
    def test_send_transactional_email_audits_api_failure(self, send):
        send.side_effect = requests.RequestException("network error")

        payload = self.transactional_email_payload()
        result = send_transactional_email(payload)

        self.assertIsNone(result)
        self.assert_transactional_send_called(send)
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.send_type, DatamailerSendAuditType.TRANSACTIONAL)
        self.assertEqual(audit.status, DatamailerSendAuditStatus.FAILED)
        self.assertEqual(audit.idempotency_key, "welcome:student")
        self.assertEqual(audit.error, "network error")

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transactional"
    )
    def test_send_transactional_email_adds_configured_from_email(
        self, send
    ):
        send.return_value = {"id": "message-id"}
        payload = {
            "template_key": "welcome",
            "email": "student@example.com",
        }

        send_transactional_email(payload)

        expected_payload = {
            "audience": "dtc-courses",
            "client": "dtc-courses",
            "template_key": "welcome",
            "email": "student@example.com",
            "from_email": "courses",
        }
        send.assert_called_once_with(expected_payload)

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transactional"
    )
    def test_send_transactional_email_keeps_explicit_from_email(
        self, send
    ):
        send.return_value = {"id": "message-id"}
        payload = {
            "template_key": "welcome",
            "email": "student@example.com",
            "from_email": "no-reply",
        }

        send_transactional_email(payload)

        expected_payload = {
            "audience": "dtc-courses",
            "client": "dtc-courses",
            "template_key": "welcome",
            "email": "student@example.com",
            "from_email": "no-reply",
        }
        send.assert_called_once_with(expected_payload)
