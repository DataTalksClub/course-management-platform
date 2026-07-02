from django.test import Client

from accounts.models import CustomUser, Token
from courses.models import RegistrationCampaign

from .registration_campaign_base import RegistrationCampaignAPITestBase


class RegistrationCampaignAuthAPITestCase(RegistrationCampaignAPITestBase):
    def non_staff_client(self):
        non_staff = self.create_non_staff_user()
        token = self.create_non_staff_token(non_staff)
        return Client(HTTP_AUTHORIZATION=f"Token {token.key}")

    def create_non_staff_user(self):
        return CustomUser.objects.create(
            username="campaign-nonstaff",
            email="campaign-nonstaff@example.com",
        )

    def create_non_staff_token(self, non_staff):
        return Token.objects.create(user=non_staff)

    def assert_staff_token_required(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "staff_token_required")

    def non_staff_admin_responses(self, client):
        create_payload = {
            "slug": "nonstaff-campaign",
            "title": "Nonstaff Campaign",
        }
        create_response = self.post_campaign(client, create_payload)
        patch_payload = {"title": "Changed by nonstaff"}
        patch_response = self.patch_campaign(client, patch_payload)
        registrations_response = client.get(self.campaign_registrations_url())
        responses = []
        responses.append(create_response)
        responses.append(patch_response)
        responses.append(registrations_response)
        return responses

    def test_registration_campaign_api_requires_auth(self):
        client = Client()
        response = client.get(self.campaign_list_url())

        self.assertEqual(response.status_code, 401)

    def test_registration_campaign_admin_operations_require_staff_token(
        self,
    ):
        campaign = self.create_campaign()
        self.create_registration(campaign)
        client = self.non_staff_client()

        for response in self.non_staff_admin_responses(client):
            self.assert_staff_token_required(response)

        nonstaff_campaign_exists = RegistrationCampaign.objects.filter(
            slug="nonstaff-campaign",
        ).exists()
        self.assertFalse(nonstaff_campaign_exists)
        campaign.refresh_from_db()
        self.assertEqual(campaign.title, "LLM Zoomcamp")
