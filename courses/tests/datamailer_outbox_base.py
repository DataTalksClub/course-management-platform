from datetime import timedelta
from unittest.mock import Mock

import requests
from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from data.models import (
    DatamailerOutboxDispatchRun,
    DatamailerOutboxDispatchRunStatus,
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)
from course_management.datamailer.sync.memberships import (
    sync_enrollment_to_datamailer,
)
from courses.models import Course, Enrollment


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


class DatamailerOutboxTestBase(TestCase):
    def http_error(self, status_code):
        exc = requests.HTTPError("request failed")
        exc.response = Mock(status_code=status_code)
        return exc

    def outbox_attempt(self, attempt_count=1, max_attempts=3):
        return Mock(attempt_count=attempt_count, max_attempts=max_attempts)
 
    def process_due_outbox(self):
        from course_management.datamailer_outbox_runs import (
            process_due_datamailer_outbox,
        )
 
        process_due_datamailer_outbox()

    def create_ml_course(self):
        return Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )

    def create_user(self, email):
        return CustomUser.objects.create_user(
            username=email,
            email=email,
            password="test",
        )

    def create_enrollment(self, user, course):
        return Enrollment.objects.create(student=user, course=course)

    def create_student_enrollment_for_ml_course(self):
        user = self.create_user("student@example.com")
        course = self.create_ml_course()
        return self.create_enrollment(user, course)

    def create_retrying_enrollment_outbox_event(self, upsert_member):
        upsert_member.side_effect = requests.RequestException("network error")
        user = self.create_user("student@example.com")
        course = self.create_ml_course()
        enrollment = self.create_enrollment(user, course)

        sync_enrollment_to_datamailer(enrollment)
        self.process_due_outbox()

        event = DatamailerOutboxEvent.objects.get()
        return event, user

    def mark_outbox_event_due(self):
        event = DatamailerOutboxEvent.objects.get()
        event.next_attempt_at = timezone.now() - timedelta(seconds=1)
        event.save(update_fields=["next_attempt_at"])
        return event

    def assert_successful_outbox_dispatch_run(self):
        run = DatamailerOutboxDispatchRun.objects.order_by("-id").first()
        self.assertEqual(run.status, DatamailerOutboxDispatchRunStatus.SUCCESS)
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(run.processed_count, 1)
        self.assertEqual(run.acked_count, 1)
        self.assertEqual(run.retrying_count, 0)
        self.assertEqual(run.failed_count, 0)

    def assert_erase_contact_outbox_event_for_user(self, event, user):
        expected_payload = {
            "email": "student@example.com",
            "audience": "dtc-courses",
            "client": "dtc-courses",
            "user_id": user.pk,
        }

        self.assertEqual(event.event_type, "contact.erase")
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(event.ordering_key, f"user:{user.pk}")
        self.assertEqual(
            event.idempotency_key,
            f"contact.erase:user:{user.pk}:student@example.com",
        )
        self.assertEqual(event.payload, expected_payload)

    def assert_erase_contact_outbox_event_for_email(self, event):
        expected_payload = {
            "email": "student@example.com",
            "audience": "dtc-courses",
            "client": "dtc-courses",
            "user_id": None,
        }

        self.assertEqual(event.event_type, "contact.erase")
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(event.ordering_key, "email:student@example.com")
        self.assertEqual(
            event.idempotency_key,
            "contact.erase:email:student@example.com:student@example.com",
        )
        self.assertEqual(event.payload, expected_payload)

    def assert_retrying_membership_outbox_event(self, event, user):
        self.assertEqual(
            event.event_type,
            "recipient_list.member_upsert",
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.RETRYING)
        self.assertEqual(event.attempt_count, 1)
        self.assertIn("network error", event.last_error)
        self.assertEqual(event.ordering_key, f"user:{user.pk}")

    def create_successful_send_audit(self):
        audit_data = {
            "send_type": DatamailerSendAuditType.TRANSACTIONAL,
            "status": DatamailerSendAuditStatus.SUCCEEDED,
            "idempotency_key": "registration:1",
            "template_key": "registration-confirmation",
            "category_tag": "course-updates",
            "event": "registration",
            "intended_count": 1,
            "created_count": 1,
            "enqueued_count": 1,
        }
        DatamailerSendAudit.objects.create(**audit_data)

    def create_failed_send_audit(self):
        audit_data = {
            "send_type": DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
            "status": DatamailerSendAuditStatus.FAILED,
            "idempotency_key": "deadline-reminder:homework:1:24h",
            "template_key": "deadline-reminder",
            "category_tag": "deadline-reminders",
            "event": "deadline_reminder",
            "list_key": "deadline-reminders:homework:ml-zoomcamp:hw1:24h",
            "intended_count": 3,
            "error": "network error",
        }
        DatamailerSendAudit.objects.create(**audit_data)
