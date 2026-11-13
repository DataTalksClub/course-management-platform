import ast
import inspect
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from course_management.datamailer.client_recipient_lists import (
    DatamailerRecipientListSendClient,
)
from courses.models.course import Course, EmailCampaign, RegistrationCampaign


class RelayClientContractTest(TestCase):
    def test_transient_send_does_not_chunk_or_pace(self):
        source = inspect.getsource(
            DatamailerRecipientListSendClient.send_to_transient_list
        )
        self.assertNotIn("chunk_payload_by_members", source)
        self.assertNotIn("PacedMemberRequest", source)
        self.assertNotIn("ThreadPoolExecutor", source)

    def test_no_campaign_loop_calling_transactional_send(self):
        root = Path(__file__).resolve().parents[2]
        for rel in (
            "courses/management/commands/send_deadline_reminders.py",
            "course_management/datamailer/sync/score_notifications.py",
            "cadmin/views/campaign_datamailer.py",
        ):
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.For, ast.AsyncFor)):
                    body_src = ast.unparse(node)
                    self.assertNotIn("/api/transactional/send", body_src, msg=rel)
                    self.assertNotIn("send_transactional", body_src, msg=rel)

    @override_settings(
        RELAY_URL="https://relay.test",
        RELAY_API_KEY="test-key",
        RELAY_CLIENT="dtc-courses",
        RELAY_AUDIENCE="datatalksclub",
    )
    def test_cadmin_campaign_edit_displays_relay_status_counts(self):
        staff = get_user_model().objects.create_user(
            username="staff",
            email="staff@example.com",
            password="pass",
            is_staff=True,
        )
        self.client.force_login(staff)
        course = Course.objects.create(
            slug="ml-zoomcamp-2026", title="ML Zoomcamp 2026"
        )
        reg_campaign = RegistrationCampaign.objects.create(
            slug="ml-2026",
            title="ML 2026",
            current_course=course,
        )
        email_campaign = EmailCampaign.objects.create(
            registration_campaign=reg_campaign,
            external_key="ml-2026-launch",
            subject="Launch",
            body_markdown="Hello",
        )
        relay_payload = {
            "campaign": {
                "external_key": "ml-2026-launch",
                "status": "sending",
                "recipient_count": 100,
                "sent_count": 60,
                "delivered_count": 55,
                "skipped_count": 5,
                "pending_count": 35,
            }
        }
        with patch(
            "course_management.datamailer.client_campaigns.DatamailerCampaignClient.campaign",
            return_value=relay_payload,
        ):
            url = reverse(
                "cadmin_email_campaign_edit",
                kwargs={
                    "campaign_slug": reg_campaign.slug,
                    "email_campaign_id": email_campaign.id,
                },
            )
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-relay-campaign-status")
        self.assertContains(response, "Sent (Relay)")
        self.assertContains(response, "60")
        self.assertContains(response, "Delivered (Relay)")
        self.assertContains(response, "55")
        self.assertContains(response, "Pending (Relay)")
        self.assertContains(response, "35")
