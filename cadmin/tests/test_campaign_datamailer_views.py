from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from cadmin.tests.campaign_view_base import (
    DATAMAILER_SETTINGS,
    CampaignCadminViewBase,
    admin_credentials,
)


class CampaignDatamailerCadminViewTests(CampaignCadminViewBase):
    @override_settings(
        **DATAMAILER_SETTINGS,
        PUBLIC_BASE_URL="https://courses.example.com",
    )
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.upsert_campaign"
    )
    def test_campaign_edit_syncs_datamailer_campaign_draft(
        self, upsert_campaign
    ):
        campaign = self.create_llm_registration_campaign(
            meta_description="Learn LLMs",
            marketing_markdown="## Register now",
        )
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        payload = {"datamailer_action": "sync"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        self.assert_campaign_draft_upserted(upsert_campaign)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.preview_campaign"
    )
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.upsert_campaign"
    )
    def test_campaign_edit_previews_datamailer_campaign(
        self, upsert_campaign, preview_campaign
    ):
        preview_campaign.return_value = {
            "preview": {
                "subject": "Preview subject",
                "text": "Preview text",
            }
        }
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        payload = {"datamailer_action": "preview"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        upsert_campaign.assert_called_once()
        preview_campaign.assert_called_once_with(
            "cmp-registration-llm-zoomcamp"
        )
        self.assertContains(response, "Preview subject")
        self.assertContains(response, "Preview text")

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.test_send_campaign"
    )
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.upsert_campaign"
    )
    def test_campaign_edit_sends_datamailer_campaign_test(
        self, upsert_campaign, test_send_campaign
    ):
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
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
            "cmp-registration-llm-zoomcamp",
            expected_recipients,
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.queue_campaign"
    )
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.upsert_campaign"
    )
    def test_campaign_edit_queues_datamailer_campaign(
        self, upsert_campaign, queue_campaign
    ):
        queue_campaign.return_value = {"recipient_count": 42}
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        payload = {"datamailer_action": "queue"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        upsert_campaign.assert_called_once()
        queue_campaign.assert_called_once_with(
            "cmp-registration-llm-zoomcamp"
        )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.cancel_campaign"
    )
    @patch(
        "cadmin.views.campaign_datamailer.DatamailerClient.upsert_campaign"
    )
    def test_campaign_edit_cancels_datamailer_campaign_without_upsert(
        self, upsert_campaign, cancel_campaign
    ):
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        payload = {"datamailer_action": "cancel"}

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        upsert_campaign.assert_not_called()
        cancel_campaign.assert_called_once_with(
            "cmp-registration-llm-zoomcamp"
        )
