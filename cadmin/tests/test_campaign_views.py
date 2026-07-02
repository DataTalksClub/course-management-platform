from django.urls import reverse

from courses.models import CourseRegistration, RegistrationCampaign
from cadmin.tests.campaign_view_base import (
    CampaignCadminViewBase,
    admin_credentials,
    credentials,
)


class CampaignCadminViewTests(CampaignCadminViewBase):
    def test_campaign_registrations_staff_allowed(self):
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
        )
        CourseRegistration.objects.create(
            campaign=campaign,
            course=self.course,
            email="student@example.com",
            name="Student One",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
        )

        self.client.login(**admin_credentials)
        url = reverse(
            "cadmin_campaign_registrations",
            kwargs={"campaign_slug": campaign.slug},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LLM Zoomcamp")
        self.assertContains(response, "student@example.com")
        self.assertContains(response, "Europe")

    def test_campaign_create_staff_allowed(self):
        self.client.login(**admin_credentials)
        url = reverse("cadmin_campaign_create")
        response = self.client.get(f"{url}?course={self.course.slug}")

        self.assert_campaign_create_page(response)

        payload = self.campaign_create_payload()
        response = self.client.post(url, payload)

        campaign = RegistrationCampaign.objects.get(slug="llm-zoomcamp")
        redirect_url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )
        self.assertRedirects(response, redirect_url)
        self.assert_created_campaign_saved(campaign)

    def test_campaign_create_non_staff_denied(self):
        self.client.login(**credentials)
        url = reverse("cadmin_campaign_create")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        campaign_exists = RegistrationCampaign.objects.exists()
        self.assertFalse(campaign_exists)

    def test_campaign_edit_staff_allowed(self):
        campaign = self.create_llm_registration_campaign(
            marketing_markdown="Old copy",
        )
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assert_campaign_edit_page(response)

        payload = self.campaign_edit_payload()
        response = self.client.post(url, payload)

        self.assertRedirects(response, url)
        self.assert_campaign_updated(campaign)

    def test_campaign_edit_shows_datamailer_campaign_controls(self):
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Datamailer campaign")
        self.assertContains(response, "cmp-registration-llm-zoomcamp")
        self.assertContains(response, self.course.slug)
        self.assertContains(response, "Sync draft")
        self.assertContains(response, "Test send")
