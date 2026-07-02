from django.test import override_settings

from data.models import DatamailerContactEvent

from .datamailer_webhook_base import DatamailerWebhookTestBase


class DatamailerWebhookTransactionalEventTest(DatamailerWebhookTestBase):
    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_records_transactional_failure_event(self):
        payload = {
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

        response = self.post_event(payload)

        self.assertEqual(response.status_code, 200)
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.event_type, "transactional.failed")
        self.assertEqual(
            event.payload["metadata"]["transactional_message_id"],
            123,
        )

    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_records_transactional_skipped_event(self):
        payload = {
            "event_id": "evt-tx-skipped-1",
            "event_type": "transactional.skipped",
            "email": "student@example.com",
            "metadata": {"reason": "hard_bounce"},
        }

        response = self.post_event(payload)

        self.assertEqual(response.status_code, 200)
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.event_type, "transactional.skipped")


class DatamailerWebhookMessageEventTest(DatamailerWebhookTestBase):
    @override_settings(DATAMAILER_WEBHOOK_TOKEN="secret-token")
    def test_webhook_records_message_lifecycle_event(self):
        payload = {
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

        response = self.post_event(payload)

        self.assertEqual(response.status_code, 200)
        event = DatamailerContactEvent.objects.get()
        self.assertEqual(event.event_type, "message.clicked")
        self.assertEqual(event.payload["metadata"]["url"], "https://example.com/path")
