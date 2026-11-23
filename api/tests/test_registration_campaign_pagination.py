from courses.models import CourseRegistration

from .registration_campaign_base import RegistrationCampaignAPITestBase


class RegistrationCampaignPaginationTest(RegistrationCampaignAPITestBase):
    def setUp(self):
        super().setUp()
        self.campaign = self.create_campaign()
        for index in range(7):
            registration = self.create_registration(
                self.campaign, email=f"s{index}@example.com"
            )
            CourseRegistration.objects.filter(pk=registration.pk).update(
                status="approved",
                accepted_nebius_sharing=index % 3 != 0,
                linkedin_url=f"https://linkedin.com/in/s{index}",
            )

    def get(self, **params):
        response = self.client.get(self.campaign_registrations_url(), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_offset_pages_cover_every_row_once(self):
        seen = []
        offset = 0
        while True:
            data = self.get(status="approved", limit=3, offset=offset)
            self.assertEqual(data["count"], 7)
            if not data["registrations"]:
                break
            seen.extend(row["id"] for row in data["registrations"])
            offset += len(data["registrations"])
        self.assertEqual(len(seen), 7)
        self.assertEqual(len(set(seen)), 7)

    def test_consent_filter_and_fields(self):
        data = self.get(accepted_nebius_sharing="true", limit=500)
        self.assertEqual(data["count"], 4)
        row = data["registrations"][0]
        self.assertIs(row["accepted_nebius_sharing"], True)
        self.assertTrue(row["linkedin_url"].startswith("https://linkedin.com"))
        for field in ("github_url", "auto_approved_at", "accepted_newsletter"):
            self.assertIn(field, row)
        self.assertEqual(self.get(accepted_nebius_sharing="false")["count"], 3)

    def test_negative_offset_is_rejected(self):
        response = self.client.get(
            self.campaign_registrations_url(), {"offset": "-1"}
        )
        self.assertEqual(response.status_code, 400)
