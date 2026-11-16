from unittest import mock

from allauth.account.models import EmailAddress
from django.core import mail

from accounts.models import CustomUser
from api.tests.registration_campaign_base import RegistrationCampaignAPITestBase
from courses.models import (
    ApplicationNotification,
    CourseRegistration,
    Enrollment,
    RegistrationCampaign,
)


class ChangeEmailTests(RegistrationCampaignAPITestBase):
    def setUp(self):
        super().setUp()
        self.campaign = RegistrationCampaign.objects.create(
            slug="genmedia", title="GenMedia", current_course=self.course,
        )
        self.reg = self.make_reg("stoic@hey.com", "approved")

    def make_reg(self, email, status="pending"):
        return CourseRegistration.objects.create(
            campaign=self.campaign, course=self.course, email=email,
            status=status,
        )

    def url(self, reg=None):
        reg = reg or self.reg
        return (f"/api/registration-campaigns/genmedia/registrations/"
                f"{reg.id}/change-email/")

    def post(self, body, reg=None):
        return self.client.post(
            self.url(reg), data=body, content_type="application/json",
        )

    def test_happy_path_links_user_enrolls_no_mail(self):
        user = CustomUser.objects.create(
            username="waldrupm@gmail.com", email="waldrupm@gmail.com",
        )
        ApplicationNotification.objects.all().delete()
        with mock.patch("courses.registration_email_change.resync_relay") as rs:
            with self.captureOnCommitCallbacks(execute=True):
                resp = self.post({"email": " WaldrupM@Gmail.com "})
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["new_email"], "waldrupm@gmail.com")
        self.assertEqual(data["user_action"], "linked")
        self.assertTrue(data["enrollment_created"])
        self.assertEqual(data["emails_queued"], 0)
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.email_normalized, "waldrupm@gmail.com")
        self.assertEqual(self.reg.user_id, user.pk)
        self.assertTrue(
            Enrollment.objects.filter(student=user, course=self.course).exists()
        )
        self.assertEqual(ApplicationNotification.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)
        rs.assert_called_once()

    def test_relay_resync_removes_old_and_syncs_new(self):
        with mock.patch(
            "course_management.datamailer.sync.membership_removals."
            "remove_registration_from_datamailer"
        ) as rm, mock.patch(
            "course_management.relay.registration.sync_registration_to_relay"
        ) as sync, mock.patch(
            "course_management.relay.registration."
            "sync_registration_to_approved_list"
        ) as approved:
            with self.captureOnCommitCallbacks(execute=True):
                self.post({"email": "new@example.com"})
        self.assertEqual(rm.call_args[0][0].email_normalized, "stoic@hey.com")
        self.assertEqual(
            sync.call_args[0][0].email_normalized, "new@example.com")
        approved.assert_called_once()

    def test_duplicate_registration_rejected(self):
        self.make_reg("taken@example.com")
        resp = self.post({"email": "Taken@example.com"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "duplicate_registration")
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.email_normalized, "stoic@hey.com")

    def test_conflicting_user_rejected(self):
        mine = CustomUser.objects.create(username="mine", email="stoic@hey.com")
        CustomUser.objects.create(username="o", email="other@example.com")
        CourseRegistration.objects.filter(pk=self.reg.pk).update(user=mine)
        resp = self.post({"email": "other@example.com"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "conflicting_user")
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.email_normalized, "stoic@hey.com")

    def test_ambiguous_owners_rejected(self):
        a = CustomUser.objects.create(username="a", email="amb@example.com")
        b = CustomUser.objects.create(username="b", email="x@example.com")
        EmailAddress.objects.create(
            user=b, email="amb@example.com", verified=True)
        resp = self.post({"email": "amb@example.com"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "conflicting_user")

    def test_updates_linked_user_email(self):
        user = CustomUser.objects.create(
            username="stoic@hey.com", email="stoic@hey.com")
        CourseRegistration.objects.filter(pk=self.reg.pk).update(user=user)
        resp = self.post({"email": "fresh@example.com"})
        self.assertEqual(resp.status_code, 200, resp.content)
        user.refresh_from_db()
        self.assertEqual(user.email, "fresh@example.com")
        self.assertEqual(user.username, "fresh@example.com")
        self.assertEqual(resp.json()["user_action"], "email_updated")
        self.assertEqual(len(mail.outbox), 0)

    def test_dry_run_changes_nothing(self):
        resp = self.post({"email": "dry@example.com", "dry_run": True})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["applied"])
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.email_normalized, "stoic@hey.com")

    def test_invalid_and_unchanged_and_non_staff(self):
        self.assertEqual(self.post({"email": "nope"}).status_code, 400)
        self.assertEqual(self.post({"email": "STOIC@hey.com"}).status_code, 409)
        self.assertEqual(self.post({"email": "a@b.co", "x": 1}).status_code, 400)
        self.user.is_staff = False
        self.user.save()
        self.assertEqual(self.post({"email": "a@b.co"}).status_code, 403)

    def test_pending_registration_not_enrolled(self):
        pending = self.make_reg("p@example.com", "pending")
        CustomUser.objects.create(username="q", email="q@example.com")
        resp = self.post({"email": "q@example.com"}, reg=pending)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Enrollment.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)
