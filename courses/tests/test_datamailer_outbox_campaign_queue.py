from unittest.mock import patch

import requests
from django.test import override_settings

from course_management.datamailer_outbox import (
    DatamailerOutboxEventData,
    enqueue_datamailer_outbox_event,
)
from courses.models import Course, EmailCampaign, RegistrationCampaign
from courses.tests.datamailer_outbox_base import (
    DATAMAILER_SETTINGS,
    DatamailerOutboxTestBase,
)
from data.models import DatamailerOutboxStatus


class DatamailerOutboxCampaignQueueTest(DatamailerOutboxTestBase):
    def create_email_campaign(self):
        course = Course.objects.create(
            slug="llm-zoomcamp-2026",
            title="LLM Zoomcamp 2026",
            description="LLM course",
        )
        registration_campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=course,
        )
        return EmailCampaign.objects.create(
            registration_campaign=registration_campaign,
            subject="Class starts Monday",
            body_markdown="Hi there",
        )

    def enqueue_queue_event(self, email_campaign):
        event_data = DatamailerOutboxEventData(
            event_type="campaign.queue",
            idempotency_key=f"email-campaign.queue:{email_campaign.id}",
            ordering_key=f"email-campaign:{email_campaign.id}",
            payload={
                "external_key": email_campaign.external_key,
                "email_campaign_id": email_campaign.id,
            },
            dispatch_immediately=False,
        )
        return enqueue_datamailer_outbox_event(event_data)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.queue_campaign"
    )
    def test_enqueue_does_not_call_datamailer(self, queue_campaign):
        email_campaign = self.create_email_campaign()

        event = self.enqueue_queue_event(email_campaign)

        queue_campaign.assert_not_called()
        self.assertEqual(event.status, DatamailerOutboxStatus.PENDING)
        email_campaign.refresh_from_db()
        self.assertEqual(email_campaign.status, EmailCampaign.Status.DRAFT)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.queue_campaign"
    )
    def test_process_outbox_queues_campaign_and_updates_email_campaign(
        self, queue_campaign
    ):
        queue_campaign.return_value = {"recipient_count": 42}
        email_campaign = self.create_email_campaign()
        event = self.enqueue_queue_event(email_campaign)

        self.process_due_outbox()

        event.refresh_from_db()
        self.assertEqual(event.status, DatamailerOutboxStatus.ACKED)
        queue_campaign.assert_called_once_with(email_campaign.external_key)

        email_campaign.refresh_from_db()
        self.assertEqual(email_campaign.status, EmailCampaign.Status.QUEUED)
        self.assertEqual(email_campaign.last_recipient_count, 42)
        self.assertIsNotNone(email_campaign.queued_at)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.queue_campaign"
    )
    def test_process_outbox_retries_on_failure_without_touching_status(
        self, queue_campaign
    ):
        queue_campaign.side_effect = requests.RequestException(
            "network error"
        )
        email_campaign = self.create_email_campaign()
        event = self.enqueue_queue_event(email_campaign)

        self.process_due_outbox()

        event.refresh_from_db()
        self.assertEqual(event.status, DatamailerOutboxStatus.RETRYING)

        email_campaign.refresh_from_db()
        self.assertEqual(
            email_campaign.status, EmailCampaign.Status.DRAFT
        )
        self.assertIsNone(email_campaign.queued_at)
