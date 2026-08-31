import json

from courses.models import EmailCampaign

from .registration_campaign_base import RegistrationCampaignAPITestBase


class EmailCampaignAPITestCase(RegistrationCampaignAPITestBase):
    def email_campaigns_url(self):
        return "/api/registration-campaigns/llm-zoomcamp/emails/"

    def post_email_campaign(self, payload):
        request_body = json.dumps(payload)
        return self.client.post(
            self.email_campaigns_url(),
            request_body,
            content_type="application/json",
        )

    def test_create_email_campaign(self):
        self.create_campaign()
        payload = {
            "subject": "Class starts Monday",
            "preview_text": "Don't miss it",
            "body_markdown": "## Hi there\n\nClass starts Monday.",
        }

        response = self.post_email_campaign(payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["subject"], "Class starts Monday")
        self.assertEqual(data["status"], EmailCampaign.Status.DRAFT)

        email_campaign = EmailCampaign.objects.get(
            registration_campaign__slug="llm-zoomcamp"
        )
        self.assertEqual(email_campaign.subject, "Class starts Monday")
        self.assertTrue(email_campaign.external_key)

    def test_create_email_campaign_requires_subject(self):
        self.create_campaign()
        response = self.post_email_campaign({"body_markdown": "Hi"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["code"], "missing_required_fields"
        )

    def test_create_email_campaign_rejects_unknown_field(self):
        self.create_campaign()
        payload = {
            "subject": "Class starts Monday",
            "status": "queued",
        }

        response = self.post_email_campaign(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_field")
        email_campaign_exists = EmailCampaign.objects.filter(
            registration_campaign__slug="llm-zoomcamp"
        ).exists()
        self.assertFalse(email_campaign_exists)

    def test_create_email_campaign_requires_staff_token(self):
        self.create_campaign()
        self.user.is_staff = False
        self.user.save()

        response = self.post_email_campaign({"subject": "Hi"})

        self.assertEqual(response.status_code, 403)

    def test_list_email_campaigns(self):
        campaign = self.create_campaign()
        EmailCampaign.objects.create(
            registration_campaign=campaign,
            subject="Class starts Monday",
        )

        response = self.client.get(self.email_campaigns_url())

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["email_campaigns"]), 1)
        self.assertEqual(
            data["email_campaigns"][0]["subject"], "Class starts Monday"
        )
