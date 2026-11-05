"""Referral program: invite link, bonus points on acceptance.

An approved applicant gets a personal invite link
(``/register/<campaign>/?ref=<registration_id>``). When an invitee who
registered through that link (or typed the inviter's email) is approved,
the inviter's enrollment earns bonus leaderboard points — exactly once.
"""

from django.test import override_settings
from django.urls import reverse

from accounts.models import CustomUser
from courses.models import CourseRegistration
from courses.models.course import Enrollment
from courses.referrals import REFERRAL_BONUS_POINTS
from courses.registration_wall import approve_registration
from courses.tests.registration_campaign_base import RegistrationCampaignBase


@override_settings(
    RELAY_URL="https://relay.example.com",
    RELAY_API_KEY="test-key",
    RELAY_CLIENT="dtc-courses",
    RELAY_AUDIENCE="dtc-courses",
)
class ReferralBonusTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        self.course.requires_registration_approval = True
        self.course.save(update_fields=["requires_registration_approval"])
        self.inviter = CustomUser.objects.create_user(
            username="inviter",
            email="inviter@example.com",
            password="test",
        )
        self.inviter_registration = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            user=self.inviter,
            email=self.inviter.email,
            name="Inviter",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
        )

    def invitee_payload(self, email="invitee@example.com"):
        payload = self.registration_payload(email=email)
        payload["experience"] = "3 years building ML systems"
        return payload

    def test_ref_link_registers_referral_silently(self):
        self.client.get(
            self.campaign_url() + f"?ref={self.inviter_registration.pk}"
        )
        payload = self.invitee_payload()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.campaign_url(), payload)
        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get(
            email="invitee@example.com"
        )
        self.assertEqual(
            registration.referred_by, self.inviter_registration
        )
        self.assertNotIn("invited_by_email", response.context["form"].fields)

    def test_unknown_ref_is_ignored(self):
        self.client.get(self.campaign_url() + "?ref=999999")
        payload = self.invitee_payload()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.campaign_url(), payload)
        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get(
            email="invitee@example.com"
        )
        self.assertIsNone(registration.referred_by)

    def test_other_campaign_ref_is_ignored(self):
        other = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="other-campaign@example.com",
            name="Other",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
        )
        session = self.client.session
        session["invite_referrers"] = {
            str(self.campaign.pk + 9999): other.pk
        }
        session.save()
        payload = self.invitee_payload()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.campaign_url(), payload)
        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get(
            email="invitee@example.com"
        )
        self.assertIsNone(registration.referred_by)

    def test_approve_awards_bonus_exactly_once(self):
        invitee = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="invitee@example.com",
            name="Invitee",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            referred_by=self.inviter_registration,
        )
        approve_registration(invitee)
        approve_registration(invitee)
        from courses.models import ReferralReward

        self.assertEqual(
            ReferralReward.objects.filter(referred=invitee).count(), 1
        )
        enrollment = Enrollment.objects.get(
            student=self.inviter, course=self.course
        )
        self.assertEqual(
            enrollment.bonus_points, REFERRAL_BONUS_POINTS
        )

    def test_bonus_survives_leaderboard_recompute(self):
        from courses.leaderboard import update_leaderboard

        enrollment = Enrollment.objects.create(
            student=self.inviter,
            course=self.course,
            bonus_points=REFERRAL_BONUS_POINTS,
        )
        update_leaderboard(self.course)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.total_score, REFERRAL_BONUS_POINTS)

    def test_approve_awards_referral_and_queues_decision_email(self):
        from courses.models import ApplicationNotification
        from courses.registration_wall import approve_registration

        invitee = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="invitee@example.com",
            name="Invitee",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            referred_by=self.inviter_registration,
        )
        approve_registration(invitee)
        enrollment = Enrollment.objects.get(
            student=self.inviter, course=self.course
        )
        self.assertEqual(
            enrollment.bonus_points, REFERRAL_BONUS_POINTS
        )
        self.assertTrue(
            ApplicationNotification.objects.filter(
                registration=invitee,
                template_key="application-approved",
            ).exists()
        )

    def test_decision_context_has_invite_url(self):
        from course_management.relay.application_notifications import (
            notification_context,
        )

        context = notification_context(self.inviter_registration)
        self.assertIn(
            f"?ref={self.inviter_registration.pk}",
            context["invite_url"],
        )
        self.assertIn("register", context["invite_url"])

    def test_approved_template_contract_includes_invite_url(self):
        from course_management.relay.application_templates import (
            TRANSACTIONAL_TEMPLATES,
        )

        # Invite section copy lives in Relay; the code contract is
        # the placeholder values CMP must send.
        spec = TRANSACTIONAL_TEMPLATES["application-approved"]
        self.assertIn("invite_url", spec["required_context"])
        self.assertIn("course_url", spec["required_context"])

    def test_course_page_shows_invite_link_to_approved(self):
        approve_registration(self.inviter_registration)
        self.client.force_login(self.inviter)
        url = reverse(
            "course", kwargs={"course_slug": self.course.slug}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, f"?ref={self.inviter_registration.pk}"
        )
