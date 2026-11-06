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


class CampaignCrossSellAttributionTests(CampaignCadminViewBase):
    def test_edit_page_shows_attribution_counts(self):
        from courses.models import CourseRegistration

        source_campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
        )
        target = RegistrationCampaign.objects.create(
            slug="ml-zoomcamp", title="ML Zoomcamp"
        )
        source = CourseRegistration.objects.create(
            campaign=source_campaign,
            course=self.course,
            email="s@example.com",
            name="S",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
        )
        CourseRegistration.objects.create(
            campaign=target,
            email="t@example.com",
            name="T",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            source="xsell-link",
            referred_by=source,
        )
        self.client.login(**admin_credentials)
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": source_campaign.slug},
        )

        page = self.client.get(url)

        self.assertContains(page, "Cross-sell signups")
        self.assertContains(page, "From here led to:")
        self.assertContains(page, "ML Zoomcamp (1)")
