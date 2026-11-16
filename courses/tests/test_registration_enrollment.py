from io import StringIO
from unittest.mock import patch

from allauth.account.models import EmailAddress
from allauth.account.signals import user_signed_up
from django.contrib.auth.signals import user_logged_in
from django.core.management import call_command
from django.test import RequestFactory
from django.urls import reverse

from accounts.models import CustomUser
from courses.models import CourseRegistration, Enrollment
from courses.registration_wall import approve_registration
from courses.tests.registration_campaign_base import RegistrationCampaignBase


class ApprovedEnrollmentTests(RegistrationCampaignBase):
    def registration(self, **kwargs):
        return CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="Student@Example.com",
            status=CourseRegistration.Status.APPROVED,
            **kwargs,
        )

    def user(self, email="student@example.com", username="student"):
        return CustomUser.objects.create_user(username=username, email=email)

    def assert_enrolled(self, registration, user):
        registration.refresh_from_db()
        self.assertEqual(registration.user_id, user.pk)
        self.assertEqual(Enrollment.objects.filter(
            course=self.course, student=user,
        ).count(), 1)

    def test_approval_before_account_then_login_repairs_course_page(self):
        registration = self.registration()
        user = self.user()
        self.client.force_login(user)
        self.assert_enrolled(registration, user)
        response = self.client.get(reverse("course", kwargs={"course_slug": self.course.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "We could not find your course enrollment")

    def test_signup_links_earlier_approval(self):
        registration = self.registration()
        user = self.user()
        user_signed_up.send(
            sender=type(user), request=RequestFactory().get("/"), user=user,
        )
        self.assert_enrolled(registration, user)

    def test_direct_approval_save_enrolls_existing_account(self):
        user = self.user()
        registration = self.registration()
        self.assert_enrolled(registration, user)

    def test_approval_matches_verified_secondary_address(self):
        user = self.user(email="other@example.com")
        EmailAddress.objects.create(
            user=user, email="student@example.com", verified=True,
        )
        registration = self.registration()
        self.assert_enrolled(registration, user)

    def test_unverified_secondary_address_does_not_grant_access(self):
        user = self.user(email="other@example.com")
        EmailAddress.objects.create(
            user=user, email="student@example.com", verified=False,
        )
        registration = self.registration()
        self.client.force_login(user)
        registration.refresh_from_db()
        self.assertIsNone(registration.user_id)
        self.assertFalse(Enrollment.objects.exists())

    def test_duplicate_email_is_not_arbitrarily_linked(self):
        self.user(username="one")
        other = self.user(username="two")
        registration = self.registration()
        approve_registration(registration)
        self.client.force_login(other)
        registration.refresh_from_db()
        self.assertIsNone(registration.user_id)
        self.assertFalse(Enrollment.objects.exists())

    def test_login_preserves_existing_owner_and_ignores_pending(self):
        owner = self.user(username="owner")
        registration = self.registration(user=owner)
        other = self.user(username="other")
        Enrollment.objects.all().delete()
        self.client.force_login(other)
        registration.refresh_from_db()
        self.assertEqual(registration.user_id, owner.pk)
        self.assertFalse(Enrollment.objects.filter(student=other).exists())
        CourseRegistration.objects.filter(pk=registration.pk).update(status="pending")
        self.client.force_login(owner)
        self.assertFalse(Enrollment.objects.exists())

    def test_login_is_idempotent_and_does_not_queue_decisions(self):
        registration = self.registration()
        user = self.user()
        with patch("course_management.relay.application_notifications.queue_application_notifications") as queue:
            for _ in range(2):
                user_logged_in.send(
                    sender=type(user), user=user,
                    request=RequestFactory().get("/"),
                )
            queue.assert_not_called()
        self.assert_enrolled(registration, user)

    def test_backfill_dry_run_and_apply_are_silent_and_idempotent(self):
        registration = self.registration()
        user = self.user()
        call_command("reconcile_registration_enrollments", stdout=StringIO())
        self.assertFalse(Enrollment.objects.exists())
        with patch("course_management.relay.application_notifications.queue_application_notifications") as queue, patch("courses.signals.sync_enrollment_recipient_list") as sync:
            with self.captureOnCommitCallbacks(execute=True):
                call_command("reconcile_registration_enrollments", apply=True, stdout=StringIO())
                call_command("reconcile_registration_enrollments", apply=True, stdout=StringIO())
            queue.assert_not_called()
            sync.assert_not_called()
        self.assert_enrolled(registration, user)
