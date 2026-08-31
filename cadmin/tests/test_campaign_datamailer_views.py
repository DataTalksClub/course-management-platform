from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from cadmin.tests.campaign_view_base import (
    DATAMAILER_SETTINGS,
    CampaignCadminViewBase,
    admin_credentials,
)
from courses.models import EmailCampaign
from data.models import DatamailerOutboxEvent, DatamailerOutboxStatus


class CampaignDatamailerCadminViewTests(CampaignCadminViewBase):
    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.upsert_campaign"
    )
    def test_email_campaign_syncs_datamailer_campaign_draft(
        self, upsert_campaign
    ):
        campaign = self.create_llm_registration_campaign()
        email_campaign = self.create_email_campaign(campaign)
        url = reverse(
            "cadmin_email_campaign_edit",
            kwargs={
                "campaign_slug": campaign.slug,
                "email_campaign_id": email_campaign.id,
            },
        )
        payload = {"datamailer_action": "sync"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        self.assert_email_campaign_draft_upserted(
            upsert_campaign, email_campaign
        )
        email_campaign.refresh_from_db()
        self.assertEqual(email_campaign.status, EmailCampaign.Status.SYNCED)

    @override_settings(
        **DATAMAILER_SETTINGS,
        DATAMAILER_FROM_EMAIL="courses",
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.upsert_campaign"
    )
    def test_email_campaign_sync_uses_configured_from_email(
        self, upsert_campaign
    ):
        campaign = self.create_llm_registration_campaign()
        email_campaign = self.create_email_campaign(campaign)
        url = reverse(
            "cadmin_email_campaign_edit",
            kwargs={
                "campaign_slug": campaign.slug,
                "email_campaign_id": email_campaign.id,
            },
        )
        payload = {"datamailer_action": "sync"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        upsert_campaign.assert_called_once()
        upserted_payload = upsert_campaign.call_args.args[1]
        self.assertEqual(upserted_payload["from_email"], "courses")

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.preview_campaign"
    )
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.upsert_campaign"
    )
    def test_email_campaign_previews_datamailer_campaign(
        self, upsert_campaign, preview_campaign
    ):
        preview_campaign.return_value = {
            "preview": {
                "subject": "Preview subject",
                "text": "Preview text",
            }
        }
        campaign = self.create_llm_registration_campaign()
        email_campaign = self.create_email_campaign(campaign)
        url = reverse(
            "cadmin_email_campaign_edit",
            kwargs={
                "campaign_slug": campaign.slug,
                "email_campaign_id": email_campaign.id,
            },
        )
        payload = {"datamailer_action": "preview"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        upsert_campaign.assert_called_once()
        preview_campaign.assert_called_once_with(
            email_campaign.external_key
        )
        self.assertContains(response, "Preview subject")
        self.assertContains(response, "Preview text")

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.test_send_campaign"
    )
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.upsert_campaign"
    )
    def test_email_campaign_sends_datamailer_campaign_test(
        self, upsert_campaign, test_send_campaign
    ):
        campaign = self.create_llm_registration_campaign()
        email_campaign = self.create_email_campaign(campaign)
        url = reverse(
            "cadmin_email_campaign_edit",
            kwargs={
                "campaign_slug": campaign.slug,
                "email_campaign_id": email_campaign.id,
            },
        )
        payload = {
            "datamailer_action": "test_send",
            "test_recipients": "ops@example.com, reviewer@example.com",
        }

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        upsert_campaign.assert_called_once()
        expected_recipients = ["ops@example.com", "reviewer@example.com"]
        test_send_campaign.assert_called_once_with(
            email_campaign.external_key,
            expected_recipients,
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.queue_campaign"
    )
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.upsert_campaign"
    )
    def test_email_campaign_queue_does_not_block_on_datamailer(
        self, upsert_campaign, queue_campaign
    ):
        campaign = self.create_llm_registration_campaign()
        email_campaign = self.create_email_campaign(campaign)
        url = reverse(
            "cadmin_email_campaign_edit",
            kwargs={
                "campaign_slug": campaign.slug,
                "email_campaign_id": email_campaign.id,
            },
        )
        payload = {"datamailer_action": "queue"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        upsert_campaign.assert_called_once()
        # The blocking part (queue_campaign) must never be called inline in
        # the request — only the async outbox dispatcher calls it.
        queue_campaign.assert_not_called()

        email_campaign.refresh_from_db()
        self.assertEqual(
            email_campaign.status, EmailCampaign.Status.QUEUE_PENDING
        )
        self.assertIsNone(email_campaign.queued_at)

        event = DatamailerOutboxEvent.objects.get(
            event_type="campaign.queue"
        )
        self.assertEqual(event.status, DatamailerOutboxStatus.PENDING)
        self.assertEqual(
            event.payload,
            {
                "external_key": email_campaign.external_key,
                "email_campaign_id": email_campaign.id,
            },
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.cancel_campaign"
    )
    @patch(
        "course_management.datamailer.client_campaigns.DatamailerCampaignClient.upsert_campaign"
    )
    def test_email_campaign_cancels_datamailer_campaign_without_upsert(
        self, upsert_campaign, cancel_campaign
    ):
        campaign = self.create_llm_registration_campaign()
        email_campaign = self.create_email_campaign(campaign)
        url = reverse(
            "cadmin_email_campaign_edit",
            kwargs={
                "campaign_slug": campaign.slug,
                "email_campaign_id": email_campaign.id,
            },
        )
        payload = {"datamailer_action": "cancel"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        upsert_campaign.assert_not_called()
        cancel_campaign.assert_called_once_with(email_campaign.external_key)
        email_campaign.refresh_from_db()
        self.assertEqual(
            email_campaign.status, EmailCampaign.Status.CANCELLED
        )
        self.assertIsNotNone(email_campaign.cancelled_at)
