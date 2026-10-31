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
            company_name="Acme Data",
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
        self.assertContains(response, "Acme Data")
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
        campaign_exists = RegistrationCampaign.objects.filter(
            slug="llm-zoomcamp"
        ).exists()
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

    def test_campaign_edit_shows_email_campaigns_section(self):
        campaign = self.create_llm_registration_campaign()
        url = reverse(
            "cadmin_campaign_edit",
            kwargs={"campaign_slug": campaign.slug},
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email campaigns")
        self.assertContains(response, "New email")
        self.assertContains(
            response,
            reverse(
                "cadmin_email_campaign_create",
                kwargs={"campaign_slug": campaign.slug},
            ),
        )


class CampaignAnalyticsTests(CampaignCadminViewBase):
    def setUp(self):
        super().setUp()
        self.campaign = RegistrationCampaign.objects.create(
            slug="agents", title="Agents", current_course=self.course
        )
        self.url = reverse(
            "cadmin_campaign_analytics",
            kwargs={"campaign_slug": self.campaign.slug},
        )
        for i, (country, nebius, confirmed) in enumerate(
            [("Germany", True, True), ("Germany", False, False), ("France", True, True)]
        ):
            CourseRegistration.objects.create(
                campaign=self.campaign,
                course=self.course,
                email=f"secret{i}@example.com",
                name=f"Secret Person {i}",
                country=country,
                region="Europe",
                role=CourseRegistration.Role.DATA_ENGINEER,
                accepted_nebius_sharing=nebius,
                email_confirmed=confirmed,
            )

    def test_requires_staff(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.login(**credentials)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_aggregates_and_no_pii(self):
        self.client.login(**admin_credentials)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 3)
        self.assertEqual(response.context["confirmed"], 2)
        self.assertEqual(response.context["nebius"], 2)
        countries = dict(response.context["breakdowns"])["Country"]
        self.assertEqual(countries[0]["label"], "Germany")
        self.assertEqual(countries[0]["count"], 2)
        self.assertNotContains(response, "secret0@example.com")
        self.assertNotContains(response, "Secret Person")

    def test_date_range_filter(self):
        self.client.login(**admin_credentials)
        response = self.client.get(self.url + "?from=2999-01-01")
        self.assertEqual(response.context["total"], 0)
        response = self.client.get(self.url + "?from=bad&to=also-bad")
        self.assertEqual(response.context["total"], 3)

    def test_linked_from_registrations_page(self):
        self.client.login(**admin_credentials)
        url = reverse(
            "cadmin_campaign_registrations",
            kwargs={"campaign_slug": self.campaign.slug},
        )
        self.assertContains(self.client.get(url), self.url)
