"""Nightly Nebius report: approved-applicant CSV emailed after the run.

Mikhail (Nebius) gets the approved list; Alexey always gets a copy.
Rejected/excluded applicants are counted, never listed.
"""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import override_settings

from courses.genmedia_policy import AUTO_APPROVAL_TIMEZONE, CAMPAIGN_SLUG
from courses.models import CourseRegistration, RegistrationCampaign
from courses.tests.registration_campaign_base import RegistrationCampaignBase


def evening_moment(hour=20, minute=5):
    zone = ZoneInfo(AUTO_APPROVAL_TIMEZONE)
    return datetime.now(zone).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


@override_settings(
    RELAY_URL="https://relay.example.com",
    RELAY_API_KEY="test-key",
    RELAY_CLIENT="dtc-courses",
    RELAY_AUDIENCE="dtc-courses",
)
class GenmediaNebiusReportTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        # Migration 0047 seeds this campaign; reuse it and point it at
        # the test course instead of creating a duplicate slug.
        self.campaign = RegistrationCampaign.objects.get(slug=CAMPAIGN_SLUG)
        self.campaign.current_course = self.course
        self.campaign.is_active = True
        self.campaign.save(update_fields=["current_course", "is_active"])

    def register(self, email, country="Germany", status="pending"):
        campaign = self.campaign
        return CourseRegistration.objects.create(
            campaign=campaign,
            course=campaign.current_course,
            email=email,
            name="Bulk",
            country=country,
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            status=status,
        )

    @patch(
        "courses.genmedia_report.send_transactional_message"
    )
    def test_completed_run_sends_report_and_copy(self, send):
        send.return_value = {"message": {"id": "9"}}
        self.register("ok@example.com")
        self.register("ru@example.com", country="Russia")
        from courses import genmedia_approval

        result = genmedia_approval.approve_pending_registrations(
            now=evening_moment()
        )
        self.assertTrue(result.ran)
        self.assertEqual(send.call_count, 2)
        recipients = sorted(
            call.args[0] for call in send.call_args_list
        )
        self.assertEqual(
            recipients,
            ["alexey.s.grigoriev@gmail.com", "mnrozhkov@nebius.com"],
        )
        payload = send.call_args_list[0].args[1]
        self.assertEqual(
            payload["template_key"], "genmedia-nebius-approval-report"
        )
        self.assertIn("ok@example.com", payload["context"]["csv_text"])
        self.assertNotIn(
            "ru@example.com", payload["context"]["csv_text"]
        )
        self.assertEqual(payload["context"]["approved_count"], 1)
        self.assertEqual(payload["context"]["excluded_count"], 1)

    @patch(
        "courses.genmedia_report.send_transactional_message"
    )
    def test_empty_run_sends_nothing(self, send):
        from courses import genmedia_approval

        result = genmedia_approval.approve_pending_registrations(
            now=evening_moment()
        )
        self.assertTrue(result.ran)
        self.assertEqual(result.approved, 0)
        send.assert_not_called()

    def test_report_template_registered(self):
        from course_management.relay.application_templates import (
            APPLICATION_TEMPLATES,
        )

        draft = APPLICATION_TEMPLATES["genmedia-nebius-approval-report"]
        field_names = [
            field["name"] for field in draft["required_context"]
        ]
        for field_name in (
            "date_label",
            "approved_count",
            "excluded_count",
            "csv_text",
        ):
            self.assertIn(field_name, field_names)
