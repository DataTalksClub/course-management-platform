from django.test import TestCase

from accounts.models import CustomUser
from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)
from courses.models import Course


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


class DatamailerContactBase(TestCase):
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
        metadata = {
            "source": "course-management-platform",
            "event": "welcome",
        }
        return {
            "template_key": "welcome",
            "email": "student@example.com",
            "idempotency_key": "welcome:student",
            "category_tag": "course-updates",
            "metadata": metadata,
        }

    def configure_transactional_send_success(self, send):
        message = {
            "id": "message-id",
            "status": "queued",
            "template_key": "welcome",
        }
        send.return_value = {
            "message": message,
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
        expected_tags = []
        expected_tags.append("course-ml-zoomcamp")
        expected_tags.append("course-cohort-ml-zoomcamp-2026")
        self.assertEqual(payload["tags"], expected_tags)
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
        counts = {
            "created": 1,
            "updated": 1,
            "unchanged": 0,
            "skipped": 0,
            "invalid": 0,
        }
        bulk_import.return_value = {"counts": counts}

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
        first_contact = first_payload["contacts"][0]
        self.assertEqual(first_contact["email"], "student1@example.com")
        self.assertEqual(
            first_contact["email_validation"]["status"],
            "externally_validated",
        )

    def assert_contact_import_output(self, out):
        output = out.getvalue()
        self.assertIn(
            "Prepared 2 contact batch(es), 2 contact(s).",
            output,
        )
        self.assertIn("Synced batch 1: 1 contact(s); created=1", output)
