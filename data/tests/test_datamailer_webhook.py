import json
from io import StringIO

from django.core.management import call_command
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
        self.assertEqual(first.json()["duplicate_count"], 0)
        self.assertEqual(second.json()["duplicate_count"], 1)
        self.assertEqual(DatamailerContactEvent.objects.count(), 1)
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.email, "student@example.com")
        self.assertEqual(event.event_type, "contact.hard_bounced")
        self.assertEqual(event.audience, "dtc-courses")
        self.assertEqual(event.duplicate_count, 1)
        self.assertIsNotNone(event.last_seen_at)
        self.assertEqual(
            event.payload["metadata"]["bounce_type"], "Permanent"
        )

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_unsubscribe_records_known_preference_without_user_update(
        self,
    ):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
        )

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
        self.assertFalse(response.json()["preference_updated"])
        user.refresh_from_db()
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.preference_key, "email_deadline_reminders")

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_unsubscribe_records_preference_from_metadata(
        self,
    ):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
        )

        response = self.post_event(
            {
                "event_id": "evt-unsub-course-updates",
                "event_type": "subscription.unsubscribed",
                "email": "student@example.com",
                "metadata": {
                    "cmp_preference_key": "email_course_updates",
                    "scope": "client",
                },
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["preference_updated"])
        user.refresh_from_db()
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.preference_key, "email_course_updates")

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_callback_status_command_reports_counts_and_duplicates(self):
        payload = {
            "event_id": "evt-1",
            "event_type": "transactional.failed",
            "email": "student@example.com",
            "metadata": {"reason": "ses_permanent_failure"},
        }
        self.post_event(payload)
        self.post_event(payload)
        self.post_event(
            {
                "event_id": "evt-2",
                "event_type": "subscription.unsubscribed",
                "email": "student@example.com",
                "preference_key": "email_course_updates",
            }
        )

        out = StringIO()
        call_command("datamailer_callback_status", stdout=out)

        output = out.getvalue()
        self.assertIn("total_events: 2", output)
        self.assertIn("duplicate_callbacks: 1", output)
        self.assertIn("transactional.failed: 1 (duplicates=1)", output)
        self.assertIn("subscription.unsubscribed: 1 (duplicates=0)", output)

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
    def test_webhook_records_message_lifecycle_event(self):
        response = self.post_event(
            {
                "event_id": "evt-message-clicked-1",
                "event_type": "message.clicked",
                "email": "student@example.com",
                "audience": "dtc-courses",
                "client": "dtc-courses",
                "metadata": {
                    "campaign_id": 123,
                    "campaign_recipient_id": 456,
                    "url": "https://example.com/path",
                },
            }
        )

        self.assertEqual(response.status_code, 200)
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.event_type, "message.clicked")
        self.assertEqual(event.payload["metadata"]["url"], "https://example.com/path")

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_records_resubscribe_without_preference_change(
        self,
    ):
        user = CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
        )

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
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.preference_key, "email_course_updates")
