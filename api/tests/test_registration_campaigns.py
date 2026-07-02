from courses.models import CourseRegistration

from .registration_campaign_base import RegistrationCampaignAPITestBase


class RegistrationCampaignAPITestCase(RegistrationCampaignAPITestBase):
    def test_create_and_patch_registration_campaign(self):
        create_payload = {
            "slug": "llm-zoomcamp",
            "title": "LLM Zoomcamp",
            "edition_label": "2026 cohort",
            "current_course": self.course.slug,
            "marketing_markdown": "Register now",
        }
        response = self.post_campaign(self.client, create_payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["slug"], "llm-zoomcamp")
        self.assertEqual(data["current_course"], self.course.slug)

        patch_payload = {
            "current_course": None,
        }
        response = self.patch_campaign(self.client, patch_payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["current_course"])

    def test_registration_campaign_registrations_stats(self):
        campaign = self.create_campaign()
        registration = self.create_registration(campaign)
        registration.role = CourseRegistration.Role.DATA_ENGINEER
        registration.save()

        url = self.campaign_registrations_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["stats"]["total"], 1)
        self.assertEqual(data["stats"]["by_region"][0]["value"], "Europe")
        self.assertEqual(
            data["registrations"][0]["email"],
            "student@example.com",
        )
