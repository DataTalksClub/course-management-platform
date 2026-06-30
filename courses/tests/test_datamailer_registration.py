from unittest.mock import patch

from django.test import TestCase, override_settings

from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)
from course_management.datamailer.keys import registration_list_key
from course_management.datamailer.payloads import (
    registration_confirmation_payload,
)
from course_management.datamailer.sync import (
    remove_registration_from_datamailer,
    send_registration_confirmation_email,
    sync_registration_to_datamailer,
)
from courses.models import Course, CourseRegistration, RegistrationCampaign


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


class DatamailerRegistrationTest(TestCase):
    def create_ml_course(self):
        return Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="Machine learning",
        )

    def create_registration(self, course=None, **overrides):
        course = course or self.create_ml_course()
        campaign = RegistrationCampaign.objects.create(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            current_course=course,
        )
        defaults = {
            "campaign": campaign,
            "course": course,
            "email": "Student@Example.com",
            "name": "Student One",
            "country": "Germany",
            "region": "Europe",
            "role": CourseRegistration.Role.DATA_ENGINEER,
            "accepted_newsletter": True,
        }
        defaults.update(overrides)
        return CourseRegistration.objects.create(**defaults)

    def create_llm_registration_for_confirmation(self):
        course = Course.objects.create(
            slug="llm-zoomcamp-2026",
            title="LLM Zoomcamp 2026",
            description="LLM course",
        )
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=course,
        )
        return CourseRegistration.objects.create(
            campaign=campaign,
            course=course,
            email="Student@Example.com",
            name="Student One",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
        )

    def configure_registration_confirmation_send_success(self, send):
        send.return_value = {
            "message": {
                "id": "message-id",
                "status": "queued",
                "template_key": "registration-confirmation",
            },
            "enqueued": True,
        }

    def assert_registration_confirmation_payload(self, payload, registration):
        self.assertEqual(payload["email"], "student@example.com")
        self.assertEqual(payload["template_key"], "registration-confirmation")
        self.assertEqual(payload["category_tag"], "course-updates")
        self.assertEqual(
            payload["idempotency_key"],
            f"registration-confirmation:{registration.pk}",
        )
        self.assertEqual(
            payload["context"]["registration_url"],
            "https://courses.example.com/register/llm-zoomcamp/",
        )
        self.assertEqual(
            payload["context"]["course_url"],
            "https://courses.example.com/llm-zoomcamp-2026/",
        )
        self.assertEqual(payload["metadata"]["event"], "course_registration")
        self.assertEqual(
            payload["metadata"]["preference_key"],
            "email_course_updates",
        )

    def assert_registration_confirmation_audit(self):
        audit = DatamailerSendAudit.objects.get()
        self.assertEqual(
            audit.send_type,
            DatamailerSendAuditType.TRANSACTIONAL,
        )
        self.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
        self.assertEqual(audit.template_key, "registration-confirmation")
        self.assertEqual(audit.category_tag, "course-updates")
        self.assertEqual(audit.event, "course_registration")

    def assert_registration_contact_synced(self, upsert_contact):
        upsert_contact.assert_called_once()
        self.assertEqual(
            upsert_contact.call_args.args[0]["tags"],
            ["course-ml-zoomcamp", "course-cohort-ml-zoomcamp-2026"],
        )

    def assert_registration_member_synced(self, upsert_member, registration):
        upsert_member.assert_called_once()
        self.assertEqual(
            upsert_member.call_args.args[0],
            registration_list_key(registration),
        )
        self.assertEqual(
            upsert_member.call_args.args[1],
            f"registration:{registration.pk}",
        )
        self.assertEqual(
            upsert_member.call_args.args[2]["member"]["email"],
            "student@example.com",
        )

    def assert_registration_outbox_event(self, registration):
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(
            event.event_type,
            "recipient_list.member_upsert",
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(event.ordering_key, "email:student@example.com")
        self.assertEqual(
            event.payload["list_key"], registration_list_key(registration)
        )
        self.assertEqual(
            event.payload["source_object_key"],
            f"registration:{registration.pk}",
        )

    def assert_registration_member_removed(self, remove_member, registration):
        remove_member.assert_called_once()
        self.assertEqual(
            remove_member.call_args.args[0],
            registration_list_key(registration),
        )
        self.assertEqual(
            remove_member.call_args.args[1],
            f"registration:{registration.pk}",
        )
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(
            event.event_type,
            "recipient_list.member_remove",
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        self.assertEqual(
            event.payload["member_payload"]["member"]["status"],
            "removed",
        )

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_registration_confirmation_payload(self):
        registration = self.create_llm_registration_for_confirmation()

        payload = registration_confirmation_payload(registration)

        self.assert_registration_confirmation_payload(payload, registration)

    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.send_transactional"
    )
    def test_send_registration_confirmation_email_uses_transactional_send(
        self, send
    ):
        self.configure_registration_confirmation_send_success(send)
        registration = self.create_llm_registration_for_confirmation()

        result = send_registration_confirmation_email(registration)

        self.assertEqual(result["message"]["id"], "message-id")
        send.assert_called_once()
        self.assert_registration_confirmation_payload(
            send.call_args.args[0],
            registration,
        )
        self.assert_registration_confirmation_audit()

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_recipient_list_member"
    )
    @patch(
        "course_management.datamailer.client.DatamailerClient.upsert_contact"
    )
    def test_sync_registration_adds_contact_and_registrant_member(
        self,
        upsert_contact,
        upsert_member,
    ):
        registration = self.create_registration()

        sync_registration_to_datamailer(registration)

        self.assert_registration_contact_synced(upsert_contact)
        self.assert_registration_member_synced(upsert_member, registration)
        self.assert_registration_outbox_event(registration)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.remove_recipient_list_member"
    )
    def test_remove_registration_deletes_registrant_member(
        self,
        remove_member,
    ):
        registration = self.create_registration()

        remove_registration_from_datamailer(registration)

        self.assert_registration_member_removed(remove_member, registration)
