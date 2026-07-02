import json

from django.test import Client, TestCase

from accounts.models import CustomUser, Token
from courses.models import Course, CourseRegistration, RegistrationCampaign


class RegistrationCampaignAPITestBase(TestCase):
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

    def campaign_list_url(self):
        return "/api/registration-campaigns/"

    def campaign_detail_url(self):
        return "/api/registration-campaigns/llm-zoomcamp/"

    def campaign_registrations_url(self):
        return "/api/registration-campaigns/llm-zoomcamp/registrations/"

    def post_campaign(self, client, payload):
        url = self.campaign_list_url()
        request_body = json.dumps(payload)
        return client.post(
            url,
            request_body,
            content_type="application/json",
        )

    def patch_campaign(self, client, payload):
        url = self.campaign_detail_url()
        request_body = json.dumps(payload)
        return client.patch(
            url,
            request_body,
            content_type="application/json",
        )
