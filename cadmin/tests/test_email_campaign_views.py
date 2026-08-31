from django.urls import reverse

from cadmin.tests.campaign_view_base import (
    CampaignCadminViewBase,
    admin_credentials,
)
from courses.models import EmailCampaign


class EmailCampaignCadminViewTests(CampaignCadminViewBase):
    def test_campaign_edit_lists_email_campaigns(self):
        campaign = self.create_llm_registration_campaign()
        email_campaign = self.create_email_campaign(
            campaign, subject="Doors close soon"
        )
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Doors close soon")
        self.assertContains(
            response,
            reverse(
                "cadmin_email_campaign_edit",
                kwargs={
                    "campaign_slug": campaign.slug,
                    "email_campaign_id": email_campaign.id,
                },
            ),
        )

    def test_campaign_edit_shows_empty_state_with_no_emails(self):
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No email campaigns yet")

    def test_email_campaign_create_prefills_subject_from_campaign_title(
        self,
    ):
        campaign = self.create_llm_registration_campaign(
            title="LLM Zoomcamp"
        )
        url = reverse(
            "cadmin_email_campaign_create",
            kwargs={"campaign_slug": campaign.slug},
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LLM Zoomcamp")

    def test_email_campaign_create_saves_and_redirects_to_edit(self):
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_email_campaign_create",
            kwargs={"campaign_slug": campaign.slug},
        )
        payload = {
            "subject": "Class starts Monday",
            "preview_text": "Don't miss it",
            "body_markdown": "## Hi there\n\nClass starts Monday.",
        }

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        email_campaign = EmailCampaign.objects.get(
            registration_campaign=campaign
        )
        self.assertRedirects(
            response,
            reverse(
                "cadmin_email_campaign_edit",
                kwargs={
                    "campaign_slug": campaign.slug,
                    "email_campaign_id": email_campaign.id,
                },
            ),
        )
        self.assertEqual(email_campaign.subject, "Class starts Monday")
        self.assertEqual(email_campaign.preview_text, "Don't miss it")
        self.assertEqual(
            email_campaign.body_markdown,
            "## Hi there\n\nClass starts Monday.",
        )
        self.assertEqual(email_campaign.status, EmailCampaign.Status.DRAFT)
        self.assertTrue(email_campaign.external_key)

    def test_email_campaign_edit_saves_changes(self):
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
            "subject": "Updated subject",
            "preview_text": "Updated preview",
            "body_markdown": "Updated body",
        }

        self.client.login(**admin_credentials)
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        email_campaign.refresh_from_db()
        self.assertEqual(email_campaign.subject, "Updated subject")
        self.assertEqual(email_campaign.preview_text, "Updated preview")
        self.assertEqual(email_campaign.body_markdown, "Updated body")

    def test_email_campaign_external_key_is_unique_per_email(self):
        campaign = self.create_llm_registration_campaign()
        first = self.create_email_campaign(campaign, subject="First")
        second = self.create_email_campaign(campaign, subject="Second")

        self.assertNotEqual(first.external_key, second.external_key)
