from django.test import override_settings

from data.models import DatamailerContactEvent

from .datamailer_webhook_base import DatamailerWebhookTestBase


class DatamailerWebhookUnsubscribePreferenceTest(
    DatamailerWebhookTestBase,
):
    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_unsubscribe_records_known_preference(self):
        user = self.create_student_user()
        payload = {
            "event_id": "evt-unsub-1",
            "event_type": "subscription.unsubscribed",
            "email": "student@example.com",
            "preference_key": "email_deadline_reminders",
            "metadata": {"scope": "client"},
        }

        response = self.post_event(payload)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertFalse(response_data["preference_updated"])
        user.refresh_from_db()
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.preference_key, "email_deadline_reminders")

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_unsubscribe_records_preference_from_metadata(self):
        user = self.create_student_user()
        metadata = {
            "cmp_preference_key": "email_course_updates",
            "scope": "client",
        }
        payload = {
            "event_id": "evt-unsub-course-updates",
            "event_type": "subscription.unsubscribed",
            "email": "student@example.com",
            "metadata": metadata,
        }

        response = self.post_event(payload)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertFalse(response_data["preference_updated"])
        user.refresh_from_db()
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.preference_key, "email_course_updates")


class DatamailerWebhookUnsubscribeEventTest(DatamailerWebhookTestBase):
    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_unsubscribe_without_preference_only_records_event(self):
        user = self.create_student_user()
        payload = {
            "event_id": "evt-unsub-2",
            "event_type": "subscription.unsubscribed",
            "email": "student@example.com",
            "metadata": {"scope": "client"},
        }

        response = self.post_event(payload)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertFalse(response_data["preference_updated"])
        user.refresh_from_db()
        event_count = DatamailerContactEvent.objects.count()
        self.assertEqual(event_count, 1)


class DatamailerWebhookResubscribeTest(DatamailerWebhookTestBase):
    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_records_resubscribe_without_preference_change(self):
        user = self.create_student_user()
        payload = {
            "event_id": "evt-resub-1",
            "event_type": "subscription.resubscribed",
            "email": "student@example.com",
            "preference_key": "email_course_updates",
        }

        response = self.post_event(payload)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertFalse(response_data["preference_updated"])
        user.refresh_from_db()
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.preference_key, "email_course_updates")
