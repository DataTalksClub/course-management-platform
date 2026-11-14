from unittest.mock import patch

from django.test import TestCase, override_settings

from accounts.models import CustomUser
from course_management.datamailer.payloads.email_campaigns import (
    email_campaign_datamailer_payload,
)
from courses.models import (
    Course,
    CourseRegistration,
    EmailCampaign,
    RegistrationCampaign,
)
from courses.registration_wall import approve_registration

RELAY_SETTINGS = {
    "RELAY_URL": "https://relay.example.com",
    "RELAY_API_KEY": "secret-token",
    "RELAY_CLIENT": "dtc-courses",
    "RELAY_AUDIENCE": "dtc-courses",
}


def make_campaign(wall):
    course = Course.objects.create(
        slug="agents-2026",
        title="Agents 2026",
        description="d",
        requires_registration_approval=wall,
    )
    campaign = RegistrationCampaign.objects.create(
        slug="agents", title="Agents", current_course=course
    )
    return course, campaign


class CampaignTargetsApprovedListTest(TestCase):
    def test_wall_course_targets_approved_list(self):
        course, campaign = make_campaign(wall=True)
        email = EmailCampaign.objects.create(
            registration_campaign=campaign, subject="s", body_markdown="b"
        )
        payload = email_campaign_datamailer_payload(email)
        self.assertEqual(
            payload["recipient_list_key"], "agents-2026:@approved"
        )

    def test_non_wall_course_targets_course_slug(self):
        course, campaign = make_campaign(wall=False)
        email = EmailCampaign.objects.create(
            registration_campaign=campaign, subject="s", body_markdown="b"
        )
        payload = email_campaign_datamailer_payload(email)
        self.assertEqual(payload["recipient_list_key"], "agents-2026")

    def test_campaign_without_course_never_has_empty_key(self):
        campaign = RegistrationCampaign.objects.create(
            slug="orphan", title="Orphan"
        )
        email = EmailCampaign.objects.create(
            registration_campaign=campaign, subject="s", body_markdown="b"
        )
        payload = email_campaign_datamailer_payload(email)
        self.assertEqual(payload["recipient_list_key"], "orphan")


@override_settings(**RELAY_SETTINGS)
class ApprovedListAutoSyncTest(TestCase):
    def setUp(self):
        self.course, self.campaign = make_campaign(wall=True)

    def registration(self, status):
        return CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="s@example.com",
            name="S",
            status=status,
        )

    def events(self):
        from data.models import DatamailerOutboxEvent

        return [
            (e.event_type, e.payload["list_key"])
            for e in DatamailerOutboxEvent.objects.filter(
                payload__list_key="agents-2026:@approved"
            ).order_by("id")
        ]

    def test_approval_upserts_into_approved_list(self):
        reg = self.registration(CourseRegistration.Status.PENDING)
        with self.captureOnCommitCallbacks(execute=True):
            approve_registration(reg)
        self.assertIn(
            ("recipient_list.member_upsert", "agents-2026:@approved"),
            self.events(),
        )

    def test_rejection_removes_from_approved_list(self):
        reg = self.registration(CourseRegistration.Status.APPROVED)
        with self.captureOnCommitCallbacks(execute=True):
            reg.status = CourseRegistration.Status.REJECTED
            reg.save(update_fields=["status", "updated_at"])
        self.assertEqual(
            self.events()[-1],
            ("recipient_list.member_remove", "agents-2026:@approved"),
        )

    def test_deleting_approved_registration_removes_from_approved_list(self):
        reg = self.registration(CourseRegistration.Status.APPROVED)
        with self.captureOnCommitCallbacks(execute=True):
            reg.delete()
        self.assertEqual(
            self.events()[-1],
            ("recipient_list.member_remove", "agents-2026:@approved"),
        )
