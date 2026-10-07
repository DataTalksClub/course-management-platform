from unittest.mock import Mock

from django.test import TestCase, override_settings

from accounts.models import CustomUser
from data.models import DatamailerOutboxEvent, DatamailerOutboxStatus
from course_management.datamailer.preferences import (
    enqueue_email_preference_update_for_user,
)
from course_management.datamailer_outbox_senders import send_event

from .datamailer_settings import RELAY_SETTINGS


@override_settings(
    **RELAY_SETTINGS,
    RELAY_OUTBOX_DISPATCH_IMMEDIATELY=False,
)
class EnqueueEmailPreferenceUpdateTest(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
            password="test",
        )

    def test_enqueue_creates_pending_outbox_event(self):
        result = enqueue_email_preference_update_for_user(
            self.user,
            {"email_deadline_reminders": False},
        )

        self.assertTrue(result)
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(event.event_type, "contact.update_preferences")
        self.assertEqual(event.status, DatamailerOutboxStatus.PENDING)
        self.assertEqual(event.ordering_key, f"user:{self.user.pk}")
        self.assertTrue(
            event.idempotency_key.startswith(
                f"contact.update_preferences:user:{self.user.pk}:"
            )
        )
        self.assertEqual(
            event.payload,
            {
                "email": "student@example.com",
                "categories": [
                    {
                        "tag": "deadline-reminders",
                        "label": "Deadline reminders",
                        "enabled": False,
                    },
                ],
                "audience": "dtc-courses",
                "client": "dtc-courses",
                "user_id": self.user.pk,
            },
        )

    def test_enqueue_rejects_unknown_preference_field(self):
        result = enqueue_email_preference_update_for_user(
            self.user,
            {"email_newsletter": True},
        )

        self.assertFalse(result)
        self.assertEqual(DatamailerOutboxEvent.objects.count(), 0)

    def test_enqueue_rejects_user_without_email(self):
        emailless_user = CustomUser.objects.create_user(
            username="emailless",
            email="",
            password="test",
        )

        result = enqueue_email_preference_update_for_user(
            emailless_user,
            {"email_deadline_reminders": False},
        )

        self.assertFalse(result)
        self.assertEqual(DatamailerOutboxEvent.objects.count(), 0)


@override_settings(**RELAY_SETTINGS)
class ContactPreferenceUpdateSenderTest(TestCase):
    def test_send_event_updates_contact_preferences(self):
        client = Mock()
        categories = [
            {
                "tag": "deadline-reminders",
                "label": "Deadline reminders",
                "enabled": False,
            },
        ]

        response = send_event(
            client,
            "contact.update_preferences",
            {
                "email": "student@example.com",
                "categories": categories,
            },
        )

        client.contacts.update_contact_preferences.assert_called_once_with(
            "student@example.com",
            categories,
        )
        self.assertEqual(
            response,
            client.contacts.update_contact_preferences.return_value,
        )
