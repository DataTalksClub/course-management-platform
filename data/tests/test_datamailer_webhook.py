import json

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from data.models import DatamailerContactEvent


class DatamailerWebhookTest(TestCase):
    def post_event(self, payload, *, token="secret-token"):
        return self.client.post(
            reverse("api_datamailer_events"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_webhook_requires_configured_token(self):
        response = self.post_event(
            {
                "event_id": "evt-1",
                "event_type": "contact.hard_bounced",
                "email": "student@example.com",
            }
        )

        self.assertEqual(response.status_code, 503)

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_rejects_invalid_token(self):
        response = self.post_event(
            {
                "event_id": "evt-1",
                "event_type": "contact.hard_bounced",
                "email": "student@example.com",
            },
            token="wrong-token",
        )

        self.assertEqual(response.status_code, 401)

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
        self.assertTrue(first.json()["created"])
        self.assertFalse(second.json()["created"])
        self.assertEqual(DatamailerContactEvent.objects.count(), 1)
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.email, "student@example.com")
        self.assertEqual(event.event_type, "contact.hard_bounced")
        self.assertEqual(event.audience, "dtc-courses")
        self.assertEqual(
            event.payload["metadata"]["bounce_type"], "Permanent"
        )

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_unsubscribe_updates_known_preference(self):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
        )
        self.assertTrue(user.email_deadline_reminders)

        response = self.post_event(
            {
                "event_id": "evt-unsub-1",
                "event_type": "subscription.unsubscribed",
                "email": "student@example.com",
                "preference_key": "email_deadline_reminders",
                "metadata": {"scope": "client"},
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["preference_updated"])
        user.refresh_from_db()
        self.assertFalse(user.email_deadline_reminders)

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_unsubscribe_without_preference_only_records_event(
        self,
    ):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
        )

        response = self.post_event(
            {
                "event_id": "evt-unsub-2",
                "event_type": "subscription.unsubscribed",
                "email": "student@example.com",
                "metadata": {"scope": "client"},
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["preference_updated"])
        user.refresh_from_db()
        self.assertTrue(user.email_course_updates)
        self.assertEqual(DatamailerContactEvent.objects.count(), 1)

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_records_transactional_failure_event(self):
        response = self.post_event(
            {
                "event_id": "evt-tx-failed-1",
                "event_type": "transactional.failed",
                "email": "student@example.com",
                "audience": "dtc-courses",
                "client": "dtc-courses",
                "metadata": {
                    "transactional_message_id": 123,
                    "reason": "ses_permanent_failure",
                },
            }
        )

        self.assertEqual(response.status_code, 200)
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.event_type, "transactional.failed")
        self.assertEqual(
            event.payload["metadata"]["transactional_message_id"],
            123,
        )

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_records_transactional_skipped_event(self):
        response = self.post_event(
            {
                "event_id": "evt-tx-skipped-1",
                "event_type": "transactional.skipped",
                "email": "student@example.com",
                "metadata": {"reason": "hard_bounce"},
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            DatamailerContactEvent.objects.get().event_type,
            "transactional.skipped",
        )

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_records_resubscribe_without_preference_change(
        self,
    ):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
        )
        user.email_course_updates = False
        user.save(update_fields=["email_course_updates"])

        response = self.post_event(
            {
                "event_id": "evt-resub-1",
                "event_type": "subscription.resubscribed",
                "email": "student@example.com",
                "preference_key": "email_course_updates",
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["preference_updated"])
        user.refresh_from_db()
        self.assertFalse(user.email_course_updates)
