from unittest.mock import patch

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
        self.assertEqual(
            data["registrations"][0]["company_name"],
            "Acme Data",
        )

    @patch(
        "api.views.registration_campaign_registration_mutations."
        "sync_registration_to_datamailer"
    )
    def test_bulk_create_registrations(self, sync_datamailer):
        campaign = self.create_campaign()
        payload = {
            "registrations": [
                {
                    "email": "Renu@Example.com",
                    "name": "Renu",
                    "country": "India",
                    "role": CourseRegistration.Role.ML_ENGINEER,
                },
                {
                    "email": "invalid-email",
                },
                {
                    "email": "kim@example.com",
                    "country": "Not A Real Country",
                },
            ],
        }

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_registrations(self.client, payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["created"], 1)
        self.assertEqual(data["skipped"], 0)
        self.assertEqual(data["errors"], 2)

        registration = CourseRegistration.objects.get()
        self.assertEqual(registration.campaign, campaign)
        self.assertEqual(registration.course, self.course)
        self.assertEqual(registration.email, "renu@example.com")
        self.assertEqual(registration.region, "Asia")
        sync_datamailer.assert_called_once_with(registration)

        results_by_status = {}
        for result in data["results"]:
            results_by_status.setdefault(result["status"], []).append(result)
        self.assertEqual(len(results_by_status["created"]), 1)
        self.assertEqual(len(results_by_status["error"]), 2)
        self.assertIn("email", results_by_status["error"][0]["errors"])
        self.assertIn("country", results_by_status["error"][1]["errors"])

    @patch(
        "api.views.registration_campaign_registration_mutations."
        "sync_registration_to_datamailer"
    )
    def test_bulk_create_registrations_skips_existing(self, sync_datamailer):
        campaign = self.create_campaign()
        self.create_registration(campaign)
        payload = {
            "registrations": [
                {"email": "student@example.com", "name": "Duplicate"},
            ],
        }

        response = self.post_registrations(self.client, payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["created"], 0)
        self.assertEqual(data["skipped"], 1)
        self.assertEqual(CourseRegistration.objects.count(), 1)
        sync_datamailer.assert_not_called()
