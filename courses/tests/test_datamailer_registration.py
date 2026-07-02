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
from course_management.datamailer.payloads.registration_confirmations import (
    registration_confirmation_payload,
)
from course_management.datamailer.sync.membership_removals import (
    remove_registration_from_datamailer,
)
from course_management.datamailer.sync.memberships import (
    sync_registration_to_datamailer,
)
from course_management.datamailer.sync.notifications import (
    send_registration_confirmation_email,
)
from courses.models import Course, CourseRegistration, RegistrationCampaign


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


def create_ml_course():
    return Course.objects.create(
        slug="ml-zoomcamp-2026",
        title="ML Zoomcamp 2026",
        description="Machine learning",
    )


def create_registration(course=None, **overrides):
    course = course or create_ml_course()
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


def create_llm_registration_for_confirmation():
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


def configure_registration_confirmation_send_success(send):
    send.return_value = {
        "message": {
            "id": "message-id",
            "status": "queued",
            "template_key": "registration-confirmation",
        },
        "enqueued": True,
    }


def assert_registration_confirmation_payload(
    test_case,
    payload,
    registration,
):
    test_case.assertEqual(payload["email"], "student@example.com")
    test_case.assertEqual(payload["template_key"], "registration-confirmation")
    test_case.assertEqual(payload["category_tag"], "course-updates")
    test_case.assertEqual(
        payload["idempotency_key"],
        f"registration-confirmation:{registration.pk}",
    )
    test_case.assertEqual(
        payload["context"]["registration_url"],
        "https://courses.example.com/register/llm-zoomcamp/",
    )
    test_case.assertEqual(
        payload["context"]["course_url"],
        "https://courses.example.com/llm-zoomcamp-2026/",
    )
    test_case.assertEqual(payload["metadata"]["event"], "course_registration")
    test_case.assertEqual(
        payload["metadata"]["preference_key"],
        "email_course_updates",
    )


def assert_registration_confirmation_audit(test_case):
    audit = DatamailerSendAudit.objects.get()
    test_case.assertEqual(
        audit.send_type,
        DatamailerSendAuditType.TRANSACTIONAL,
    )
    test_case.assertEqual(audit.status, DatamailerSendAuditStatus.SUCCEEDED)
    test_case.assertEqual(audit.template_key, "registration-confirmation")
    test_case.assertEqual(audit.category_tag, "course-updates")
    test_case.assertEqual(audit.event, "course_registration")


def assert_registration_contact_synced(test_case, upsert_contact):
    upsert_contact.assert_called_once()
    test_case.assertEqual(
        upsert_contact.call_args.args[0]["tags"],
        ["course-ml-zoomcamp", "course-cohort-ml-zoomcamp-2026"],
    )


def assert_registration_member_synced(
    test_case,
    upsert_member,
    registration,
):
    upsert_member.assert_called_once()
    expected_list_key = registration_list_key(registration)
    test_case.assertEqual(
        upsert_member.call_args.args[0],
        expected_list_key,
    )
    test_case.assertEqual(
        upsert_member.call_args.args[1],
        f"registration:{registration.pk}",
    )
    test_case.assertEqual(
        upsert_member.call_args.args[2]["member"]["email"],
        "student@example.com",
    )


def assert_registration_outbox_event(test_case, registration):
    event = DatamailerOutboxEvent.objects.get()
    test_case.assertEqual(
        event.event_type,
        "recipient_list.member_upsert",
    )
    test_case.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
    test_case.assertEqual(event.ordering_key, "email:student@example.com")
    expected_list_key = registration_list_key(registration)
    test_case.assertEqual(event.payload["list_key"], expected_list_key)
    test_case.assertEqual(
        event.payload["source_object_key"],
        f"registration:{registration.pk}",
    )


def assert_registration_member_removed(
    test_case,
    remove_member,
    registration,
):
    remove_member.assert_called_once()
    expected_list_key = registration_list_key(registration)
    test_case.assertEqual(
        remove_member.call_args.args[0],
        expected_list_key,
    )
    test_case.assertEqual(
        remove_member.call_args.args[1],
        f"registration:{registration.pk}",
    )
    event = DatamailerOutboxEvent.objects.get()
    test_case.assertEqual(
        event.event_type,
        "recipient_list.member_remove",
    )
    test_case.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
    test_case.assertEqual(
        event.payload["member_payload"]["member"]["status"],
        "removed",
    )


class DatamailerRegistrationConfirmationPayloadTest(TestCase):
    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    def test_registration_confirmation_payload(self):
        registration = create_llm_registration_for_confirmation()

        payload = registration_confirmation_payload(registration)

        assert_registration_confirmation_payload(self, payload, registration)


class DatamailerRegistrationConfirmationSendTest(TestCase):
    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client_transactional.DatamailerTransactionalClient.send_transactional"
    )
    def test_send_registration_confirmation_email_uses_transactional_send(
        self, send
    ):
        configure_registration_confirmation_send_success(send)
        registration = create_llm_registration_for_confirmation()

        result = send_registration_confirmation_email(registration)

        self.assertEqual(result["message"]["id"], "message-id")
        send.assert_called_once()
        assert_registration_confirmation_payload(
            self,
            send.call_args.args[0],
            registration,
        )
        assert_registration_confirmation_audit(self)


class DatamailerRegistrationMembershipSyncTest(TestCase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.upsert"
    )
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.upsert_contact"
    )
    def test_sync_registration_adds_contact_and_registrant_member(
        self,
        upsert_contact,
        upsert_member,
    ):
        registration = create_registration()

        sync_registration_to_datamailer(registration)

        assert_registration_contact_synced(self, upsert_contact)
        assert_registration_member_synced(self, upsert_member, registration)
        assert_registration_outbox_event(self, registration)


class DatamailerRegistrationMembershipRemovalTest(TestCase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.remove"
    )
    def test_remove_registration_deletes_registrant_member(
        self,
        remove_member,
    ):
        registration = create_registration()

        remove_registration_from_datamailer(registration)

        assert_registration_member_removed(self, remove_member, registration)
