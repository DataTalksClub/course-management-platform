from django.test import override_settings

from data.models import DatamailerContactEvent

from .datamailer_webhook_base import DatamailerWebhookTestBase


class DatamailerWebhookAuthTest(DatamailerWebhookTestBase):
    def test_webhook_requires_configured_token(self):
        payload = {
            "event_id": "evt-1",
            "event_type": "contact.hard_bounced",
            "email": "student@example.com",
        }

        response = self.post_event(payload)

        self.assertEqual(response.status_code, 503)

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_rejects_invalid_token(self):
        payload = {
            "event_id": "evt-1",
            "event_type": "contact.hard_bounced",
            "email": "student@example.com",
        }

        response = self.post_event(payload, token="wrong-token")

        self.assertEqual(response.status_code, 401)


class DatamailerWebhookContactTest(DatamailerWebhookTestBase):
    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_records_contact_event_idempotently(self):
        payload = {
            "event_id": "evt-1",
            "event_type": "contact.hard_bounced",
            "email": "Student@Example.com",
            "occurred_at": "2026-06-18T10:00:00Z",
            "audience": "dtc-courses",
            "client": "dtc-courses",
            "metadata": {"bounce_type": "Permanent"},
        }

        first = self.post_event(payload)
        second = self.post_event(payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_data = first.json()
        second_data = second.json()
        self.assertTrue(first_data["created"])
        self.assertFalse(second_data["created"])
        self.assertEqual(first_data["duplicate_count"], 0)
        self.assertEqual(second_data["duplicate_count"], 1)
        event_count = DatamailerContactEvent.objects.count()
        self.assertEqual(event_count, 1)
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.email, "student@example.com")
        self.assertEqual(event.event_type, "contact.hard_bounced")
        self.assertEqual(event.audience, "dtc-courses")
        self.assertEqual(event.duplicate_count, 1)
        self.assertIsNotNone(event.last_seen_at)
        self.assertEqual(
            event.payload["metadata"]["bounce_type"], "Permanent"
        )
