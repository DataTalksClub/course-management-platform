from io import StringIO
from unittest.mock import patch

import requests
from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import CustomUser
from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)
from course_management.datamailer.keys import contact_tags_for_course
from course_management.datamailer.payloads.base import (
    contact_payload_for_user,
)
from course_management.datamailer.payloads.send import (
    datamailer_send_counts,
)
from course_management.datamailer.sync.contacts import (
    sync_contact,
)
from course_management.datamailer.sync.transactional import (
    send_transactional_email,
)
from courses.models import Course


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


class DatamailerContactTest(TestCase):
    def create_contact_payload_fixture(self):
        user = CustomUser.objects.create(
            email="Student@Example.com",
            username="student",
        )
        course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )
        return user, course

    def transactional_email_payload(self):
        return {
            "template_key": "welcome",
            "email": "student@example.com",
            "idempotency_key": "welcome:student",
            "category_tag": "course-updates",
            "metadata": {
                "source": "course-management-platform",
                "event": "welcome",
            },
        }

    def configure_transactional_send_success(self, send):
        send.return_value = {
            "message": {
                "id": "message-id",
                "status": "queued",
                "template_key": "welcome",
            },
            "enqueued": True,
            "idempotent_replay": False,
        }

    def assert_course_subscription_contact_payload(self, payload):
        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(payload["client"], "dtc-courses")
        self.assertEqual(payload["audience"], "dtc-courses")
        self.assertEqual(payload["status"], "subscribed")
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

    def assert_transactional_send_called(self, send):
        expected_payload = self.transactional_email_payload()
        expected_payload.update(
            {
                "audience": "dtc-courses",
                "client": "dtc-courses",
            }
        )
        send.assert_called_once_with(expected_payload)

    def assert_transactional_send_audit(self):
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(audit.send_type, DatamailerSendAuditType.TRANSACTIONAL)
        self.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
        self.assertEqual(audit.idempotency_key, "welcome:student")
        self.assertEqual(audit.template_key, "welcome")
        self.assertEqual(audit.category_tag, "course-updates")
        self.assertEqual(audit.source, "course-management-platform")
        self.assertEqual(audit.event, "welcome")
        self.assertEqual(audit.intended_count, 1)
        self.assertEqual(audit.enqueued_count, 1)
        self.assertEqual(audit.skipped_count, 0)

    def configure_contact_bulk_import_counts(self, bulk_import):
        bulk_import.return_value = {
            "counts": {
                "created": 1,
                "updated": 1,
                "unchanged": 0,
                "skipped": 0,
                "invalid": 0,
            },
        }

    def create_contact_backfill_users(self):
        CustomUser.objects.create_user(
            username="student-1",
            email="Student1@Example.com",
        )
        CustomUser.objects.create_user(
            username="student-2",
            email="student2@example.com",
        )

    def assert_first_contact_import_payload(self, bulk_import):
        self.assertEqual(bulk_import.call_count, 2)
        first_payload = bulk_import.call_args_list[0].args[0]
        self.assertEqual(first_payload["audience"], "dtc-courses")
        self.assertEqual(first_payload["client"], "dtc-courses")
        self.assertEqual(
            first_payload["idempotency_key"],
            "cmp-contact-bootstrap:1",
        )
        self.assertEqual(
            first_payload["contacts"][0]["email"],
            "student1@example.com",
        )
        self.assertEqual(
            first_payload["contacts"][0]["email_validation"]["status"],
            "externally_validated",
        )

    def assert_contact_import_output(self, out):
        output = out.getvalue()
        self.assertIn(
            "Prepared 2 contact batch(es), 2 contact(s).",
            output,
        )
        self.assertIn("Synced batch 1: 1 contact(s); created=1", output)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_contact_payload_includes_course_subscription_data(self):
        user, course = self.create_contact_payload_fixture()

        payload = contact_payload_for_user(user, course=course)

        self.assert_course_subscription_contact_payload(payload)

    def test_contact_tags_for_course_without_trailing_year(self):
        course = Course(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            description="Machine learning",
        )

        tags = contact_tags_for_course(course)
        expected_tags = [
            "course-ml-zoomcamp",
            "course-cohort-ml-zoomcamp",
        ]
        self.assertEqual(tags, expected_tags)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_sync_contact_logs_and_continues_on_api_failure(
        self, upsert
    ):
        upsert.side_effect = requests.RequestException("network error")
        user = CustomUser.objects.create(email="student@example.com")

        sync_contact(user)

        upsert.assert_called_once()

    @override_settings(**DATAMAILER_SETTINGS, DATAMAILER_STRICT=True)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_sync_contact_can_be_strict(self, upsert):
        upsert.side_effect = requests.RequestException("network error")
        user = CustomUser.objects.create(email="student@example.com")

        with self.assertRaises(requests.RequestException):
            sync_contact(user)

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

    def test_datamailer_send_counts_marks_transactional_replay(self):
        payload = {}
        result = {
            "idempotent_replay": True,
            "enqueued": False,
            "message": {"status": "skipped"},
        }

        counts = datamailer_send_counts(
            DatamailerSendAuditType.TRANSACTIONAL,
            payload,
            result,
        )

        self.assertEqual(counts["intended_count"], 1)
        self.assertEqual(counts["created_count"], 0)
        self.assertEqual(counts["enqueued_count"], 0)
        self.assertEqual(counts["skipped_count"], 1)
        self.assertEqual(counts["idempotent_replay_count"], 1)

    def test_datamailer_send_counts_uses_recipient_list_response(self):
        payload = {}
        result = {
            "recipient_list": {"active_member_count": 3},
            "created_count": 2,
            "enqueued_count": 1,
            "skipped_count": 1,
        }

        counts = datamailer_send_counts(
            DatamailerSendAuditType.RECIPIENT_LIST,
            payload,
            result,
        )

        self.assertEqual(counts["intended_count"], 3)
        self.assertEqual(counts["created_count"], 2)
        self.assertEqual(counts["enqueued_count"], 1)
        self.assertEqual(counts["skipped_count"], 1)

    def test_datamailer_send_counts_falls_back_to_transient_members(self):
        payload = {
            "members": [
                {"email": "active@example.com"},
                {"email": "removed@example.com", "status": "removed"},
            ],
        }
        result = {"transient_recipient_list": {}, "enqueued_count": 1}

        counts = datamailer_send_counts(
            DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
            payload,
            result,
        )

        self.assertEqual(counts["intended_count"], 1)
        self.assertEqual(counts["enqueued_count"], 1)

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

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_import_contacts"
    )
    def test_contact_backfill_command_bulk_imports_users(
        self,
        bulk_import,
    ):
        self.configure_contact_bulk_import_counts(bulk_import)
        self.create_contact_backfill_users()

        out = StringIO()
        call_command(
            "sync_datamailer_contacts",
            "--batch-size",
            "1",
            stdout=out,
        )

        self.assert_first_contact_import_payload(bulk_import)
        self.assert_contact_import_output(out)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_import_contacts"
    )
    def test_contact_backfill_command_dry_run_does_not_call_datamailer(
        self,
        bulk_import,
    ):
        CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
        )

        out = StringIO()
        call_command("sync_datamailer_contacts", "--dry-run", stdout=out)

        bulk_import.assert_not_called()
        output = out.getvalue()
        self.assertIn("Prepared 1 contact batch(es), 1 contact(s).", output)
        self.assertIn("batch 1: 1 contact(s)", output)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.bulk_import_contacts"
    )
    def test_contact_backfill_command_can_limit_to_active_users(
        self,
        bulk_import,
    ):
        bulk_import.return_value = {"counts": {"created": 1}}
        CustomUser.objects.create_user(
            username="active",
            email="active@example.com",
        )
        CustomUser.objects.create_user(
            username="inactive",
            email="inactive@example.com",
            is_active=False,
        )

        out = StringIO()
        call_command("sync_datamailer_contacts", "--active-only", stdout=out)

        bulk_import.assert_called_once()
        payload = bulk_import.call_args.args[0]
        self.assertEqual(len(payload["contacts"]), 1)
        self.assertEqual(payload["contacts"][0]["email"], "active@example.com")
