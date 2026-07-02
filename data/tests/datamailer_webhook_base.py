import json

from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser


class DatamailerWebhookTestBase(TestCase):
    def post_event(self, payload, *, token="secret-token"):
        events_url = reverse("api_datamailer_events")
        request_body = json.dumps(payload)
        return self.client.post(
            events_url,
            data=request_body,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def create_student_user(self):
        return CustomUser.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
        )
