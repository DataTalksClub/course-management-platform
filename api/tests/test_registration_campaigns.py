import json

from django.test import Client, TestCase

from accounts.models import CustomUser, Token
from courses.models import Course, CourseRegistration, RegistrationCampaign


class RegistrationCampaignAPITestCase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            username="testuser",
            email="test@example.com",
        )
        self.token = Token.objects.create(user=self.user)
        self.client = Client()
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Token {self.token.key}"
        self.course = Course.objects.create(
            slug="llm-zoomcamp-2026",
            title="LLM Zoomcamp 2026",
            description="LLM course",
        )

    def test_create_and_patch_registration_campaign(self):
        response = self.client.post(
            "/api/registration-campaigns/",
            json.dumps({
                "slug": "llm-zoomcamp",
                "title": "LLM Zoomcamp",
                "edition_label": "2026 cohort",
                "current_course": self.course.slug,
                "marketing_markdown": "Register now",
                "mailchimp_tag_before_switch": "llm-zoomcamp-2026",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["slug"], "llm-zoomcamp")
        self.assertEqual(data["current_course"], self.course.slug)
        self.assertEqual(
            data["selected_mailchimp_tag"],
            "llm-zoomcamp-2026",
        )

        response = self.client.patch(
            "/api/registration-campaigns/llm-zoomcamp/",
            json.dumps({
                "mailchimp_tag_after_switch": "llm-zoomcamp-next",
                "current_course": None,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["current_course"])
        self.assertEqual(
            data["mailchimp_tag_after_switch"],
            "llm-zoomcamp-next",
        )

    def test_registration_campaign_registrations_stats(self):
        campaign = RegistrationCampaign.objects.create(
            slug="llm-zoomcamp",
            title="LLM Zoomcamp",
            current_course=self.course,
        )
        CourseRegistration.objects.create(
            campaign=campaign,
            course=self.course,
            email="student@example.com",
            name="Student",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            accepted_newsletter=True,
        )

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
