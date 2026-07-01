import json

from django.test import Client, TestCase

from accounts.models import CustomUser, Token
from courses.models import Course, CourseRegistration, RegistrationCampaign


class RegistrationCampaignAPITestCase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="test@example.com",
            is_staff=True,
        )
        self.token = Token.objects.create(user=self.user)
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Token {self.token.key}"
        self.course = Course.objects.create(
            slug="llm-zoomcamp-2026",
            title="LLM Zoomcamp 2026",
            description="LLM course",
        )

    def create_campaign(self):
        return RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
        )

    def create_registration(self, campaign):
        return CourseRegistration.objects.create(
            campaign=campaign,
            course=self.course,
            email="student@example.com",
            name="Student",
            country="Germany",
            region="Europe",
            accepted_newsletter=True,
        )

    def non_staff_client(self):
        non_staff = CustomUser.objects.create(
            username="campaign-nonstaff",
            email="campaign-nonstaff@example.com",
        )
        token = Token.objects.create(user=non_staff)
        return Client(HTTP_AUTHORIZATION=f"Token {token.key}")

    def assert_staff_token_required(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "staff_token_required")

    def non_staff_admin_responses(self, client):
        create_payload = {
            "slug": "nonstaff-campaign",
            "title": "Nonstaff Campaign",
        }
        create_body = json.dumps(create_payload)
        create_response = client.post(
            "/api/registration-campaigns/",
            create_body,
            content_type="application/json",
        )
        patch_payload = {"title": "Changed by nonstaff"}
        patch_body = json.dumps(patch_payload)
        patch_response = client.patch(
            "/api/registration-campaigns/llm-zoomcamp/",
            patch_body,
            content_type="application/json",
        )
        registrations_response = client.get(
            "/api/registration-campaigns/llm-zoomcamp/registrations/"
        )
        return create_response, patch_response, registrations_response

    def test_create_and_patch_registration_campaign(self):
        create_payload = {
            "slug": "llm-zoomcamp",
            "title": "LLM Zoomcamp",
            "edition_label": "2026 cohort",
            "current_course": self.course.slug,
            "marketing_markdown": "Register now",
        }
        create_body = json.dumps(create_payload)
        response = self.client.post(
            "/api/registration-campaigns/",
            create_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["slug"], "llm-zoomcamp")
        self.assertEqual(data["current_course"], self.course.slug)

        patch_payload = {
            "current_course": None,
        }
        patch_body = json.dumps(patch_payload)
        response = self.client.patch(
            "/api/registration-campaigns/llm-zoomcamp/",
            patch_body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["current_course"])

    def test_registration_campaign_registrations_stats(self):
        campaign = self.create_campaign()
        registration = self.create_registration(campaign)
        registration.role = CourseRegistration.Role.DATA_ENGINEER
        registration.save()

        response = self.client.get(
            "/api/registration-campaigns/llm-zoomcamp/registrations/"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["stats"]["total"], 1)
        self.assertEqual(data["stats"]["by_region"][0]["value"], "Europe")
        self.assertEqual(data["registrations"][0]["email"], "student@example.com")

    def test_registration_campaign_api_requires_auth(self):
        client = Client()
        response = client.get("/api/registration-campaigns/")

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
