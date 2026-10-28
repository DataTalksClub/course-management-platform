from django.urls import reverse

from courses.models import RegistrationCampaign
from cadmin.tests.campaign_view_base import (
    CampaignCadminViewBase,
    admin_credentials,
)


class CampaignCrossSellCadminTests(CampaignCadminViewBase):
    def test_edit_saves_suggested_courses_and_exclusion(self):
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
        )
        other = RegistrationCampaign.objects.create(
            slug="ml-zoomcamp", title="ML Zoomcamp"
        )
        self.client.login(**admin_credentials)
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )

        page = self.client.get(url)
        self.assertContains(page, "Cross-sell")
        self.assertContains(page, "ML Zoomcamp")
        self.assertNotContains(
            page, f'name="suggested_campaigns" value="{campaign.pk}"'
        )

        payload = self.campaign_create_payload()
        payload["suggested_campaigns"] = [other.pk]
        payload["exclude_from_suggestions"] = "on"
        self.client.post(url, payload)

        campaign.refresh_from_db()
        self.assertEqual(list(campaign.suggested_campaigns.all()), [other])
        self.assertTrue(campaign.exclude_from_suggestions)
