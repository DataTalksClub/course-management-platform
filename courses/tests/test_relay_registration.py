import ast
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from courses.models import CourseRegistration
from courses.tests.registration_campaign_base import (
    RegistrationCampaignBase,
)
from data.models import DatamailerOutboxEvent, DatamailerOutboxStatus


class RegistrationRelayImportTests(SimpleTestCase):
    def test_registration_view_imports_relay_modules(self):
        from courses.views import registration

        tree = ast.parse(Path(registration.__file__).read_text())
        modules = [
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertFalse(
            any(
                module.startswith("course_management.datamailer")
                for module in modules
            )
        )
        self.assertIn("course_management.relay.registration", modules)
        self.assertIn("course_management.relay.notifications", modules)


@override_settings(
    RELAY_URL="https://relay.example.com",
    RELAY_API_KEY="test-relay-key",
    RELAY_CLIENT="dtc-courses",
    RELAY_AUDIENCE="dtc-courses",
    RELAY_OUTBOX_DISPATCH_IMMEDIATELY=True,
    RELAY_STRICT=True,
)
class RegistrationRelayTests(RegistrationCampaignBase):
    def submit(self, payload=None):
        with (
            patch(
                "courses.views.registration.send_registration_confirmation_email"
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            return self.client.post(
                self.campaign_url(),
                payload or self.registration_payload(),
            )

    @patch("requests.Session.request")
    def test_submit_upserts_relay_contact_and_membership(self, request):
        request.return_value = Mock(status_code=200)
        request.return_value.json.return_value = {}

        response = self.submit()

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        self.assertTrue(registration.accepted_newsletter)
        self.assertFalse(registration.accepted_nebius_sharing)
        self.assertEqual(request.call_count, 2)
        contact, membership = request.call_args_list
        self.assertEqual(
            contact.args,
            ("POST", "https://relay.example.com/api/contacts"),
        )
        self.assertEqual(
            contact.kwargs["headers"]["Authorization"],
            "Bearer test-relay-key",
        )
        self.assertEqual(
            contact.kwargs["json"],
            {
                "email": "student@example.com",
                "audience": "dtc-courses",
                "client": "dtc-courses",
                "status": "subscribed",
                "verified": True,
                "email_validation": {"status": "externally_validated"},
                "tags": [
                    "course-llm-zoomcamp",
                    "course-cohort-llm-zoomcamp-2026",
                ],
            },
        )
        self.assertIn("/api/recipient-lists/", membership.args[1])
        member = membership.kwargs["json"]["member"]
        self.assertEqual(member["email"], "student@example.com")
        self.assertEqual(
            member["metadata"]["registration_id"], registration.pk
        )
        self.assertEqual(member["metadata"]["country"], "Germany")
        self.assertEqual(member["metadata"]["role"], "data_engineer")
        self.assertEqual(
            DatamailerOutboxEvent.objects.get().status,
            DatamailerOutboxStatus.ACKED,
        )

    @patch(
        "requests.Session.request",
        side_effect=requests.Timeout("Relay timed out"),
    )
    def test_contact_failure_is_logged_and_does_not_break_submit(
        self, request
    ):
        with self.assertLogs(
            "course_management.relay.registration", level="ERROR"
        ) as logs:
            response = self.submit()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CourseRegistration.objects.count(), 1)
        self.assertTrue(
            any(
                "Relay registration sync failed" in line
                for line in logs.output
            )
        )
        event = DatamailerOutboxEvent.objects.get()
        self.assertEqual(event.status, DatamailerOutboxStatus.RETRYING)
        self.assertEqual(event.attempt_count, 1)

    @override_settings(RELAY_API_KEY="", RELAY_STRICT=False)
    def test_missing_config_is_logged_and_does_not_break_submit(self):
        with self.assertLogs(
            "course_management.relay.registration", level="ERROR"
        ) as logs:
            response = self.submit()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any("relay_config_missing" in line for line in logs.output)
        )
        self.assertFalse(DatamailerOutboxEvent.objects.exists())

    @patch("requests.Session.request")
    def test_missing_newsletter_consent_does_not_sync(self, request):
        payload = self.registration_payload()
        payload.pop("accepted_newsletter")

        response = self.submit(payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CourseRegistration.objects.exists())
        request.assert_not_called()

    @patch("requests.Session.request")
    def test_confirmation_failure_does_not_break_submit(self, request):
        success = Mock(status_code=200)
        success.json.return_value = {}
        request.side_effect = [
            success,
            success,
            requests.Timeout("Relay timed out"),
        ]
        with (
            self.assertLogs("course_management", level="ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                self.campaign_url(), self.registration_payload()
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CourseRegistration.objects.count(), 1)
