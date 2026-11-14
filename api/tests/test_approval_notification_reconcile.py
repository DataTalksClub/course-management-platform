from django.test import Client, TestCase

from accounts.models import CustomUser, Token
from courses.models import (
    ApplicationNotification,
    Course,
    CourseRegistration,
    RegistrationCampaign,
)
from courses.registration_wall import approve_registration


class ApprovalNotificationReconcileAPITests(TestCase):
    def setUp(self):
        self.staff_user = CustomUser.objects.create(
            username="staff@example.com",
            email="staff@example.com",
            is_staff=True,
        )
        self.staff_token = Token.objects.create(user=self.staff_user)
        self.staff_headers = {"HTTP_AUTHORIZATION": f"Token {self.staff_token.key}"}

        self.non_staff_user = CustomUser.objects.create(
            username="student@example.com",
            email="student@example.com",
            is_staff=False,
        )
        self.non_staff_token = Token.objects.create(user=self.non_staff_user)
        self.non_staff_headers = {
            "HTTP_AUTHORIZATION": f"Token {self.non_staff_token.key}"
        }
        self.client = Client()

        self.course = Course.objects.create(
            slug="genmedia-2026",
            title="GenMedia 2026",
        )
        self.campaign = RegistrationCampaign.objects.create(
            slug="genmedia",
            title="GenMedia",
            current_course=self.course,
            is_active=True,
        )
        self.inactive_campaign = RegistrationCampaign.objects.create(
            slug="old-campaign",
            title="Old Campaign",
            current_course=self.course,
            is_active=False,
        )

    def test_endpoints_require_staff_token(self):
        for url in (
            "/api/datamailer/application-notifications",
            "/api/registration-campaigns/approval-notifications/reconcile/",
        ):
            self.assertEqual(self.client.get(url).status_code, 401)
            resp = self.client.get(url, **self.non_staff_headers)
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.json()["code"], "staff_token_required")

    def test_application_notifications_endpoint_filters_and_includes_registration(self):
        no_notif = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="missing@example.com",
            name="Missing",
            status=CourseRegistration.Status.PENDING,
        )
        CourseRegistration.objects.filter(pk=no_notif.pk).update(
            status=CourseRegistration.Status.APPROVED
        )

        with_notif = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="hasnotif@example.com",
            name="Has Notif",
            status=CourseRegistration.Status.PENDING,
        )
        approve_registration(with_notif)

        resp = self.client.get(
            f"/api/datamailer/application-notifications?registration_id={no_notif.pk}",
            **self.staff_headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["registration"]["id"], no_notif.pk)
        self.assertEqual(body["registration"]["status"], "approved")

        resp2 = self.client.get(
            "/api/datamailer/application-notifications?email=HASNOTIF@example.com&template_key=application-approved",
            **self.staff_headers,
        )
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.json()
        self.assertEqual(body2["count"], 1)
        self.assertEqual(body2["notifications"][0]["registration_id"], with_notif.pk)
        self.assertEqual(body2["notifications"][0]["status"], "pending")

    def test_reconcile_endpoint_diagnoses_all_missing_cases(self):
        # 1. Sent approval (excluded from missing)
        sent_reg = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="sent@example.com",
            name="Sent",
            status=CourseRegistration.Status.PENDING,
        )
        approve_registration(sent_reg)
        ApplicationNotification.objects.filter(registration=sent_reg).update(
            status=ApplicationNotification.Status.SENT,
            relay_message_id="msg-1",
        )

        # 2. Approved via update() -> no notification row
        no_row_reg = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="norow@example.com",
            name="No Row",
            status=CourseRegistration.Status.PENDING,
        )
        CourseRegistration.objects.filter(pk=no_row_reg.pk).update(
            status=CourseRegistration.Status.APPROVED
        )

        # 3. Approved with failed notification
        failed_reg = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="failed@example.com",
            name="Failed",
            status=CourseRegistration.Status.PENDING,
        )
        approve_registration(failed_reg)
        ApplicationNotification.objects.filter(registration=failed_reg).update(
            status=ApplicationNotification.Status.FAILED,
            last_error="HTTPError",
        )

        # 4. Inactive campaign approved without notification
        inactive_reg = CourseRegistration.objects.create(
            campaign=self.inactive_campaign,
            course=self.course,
            email="inactive@example.com",
            name="Inactive",
            status=CourseRegistration.Status.PENDING,
        )
        CourseRegistration.objects.filter(pk=inactive_reg.pk).update(
            status=CourseRegistration.Status.APPROVED
        )

        resp = self.client.get(
            "/api/registration-campaigns/approval-notifications/reconcile/",
            **self.staff_headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["totals"]["approved_count"], 3)
        self.assertEqual(data["totals"]["sent_count"], 1)
        self.assertEqual(data["totals"]["missing_count"], 2)
        by_slug = {c["slug"]: c for c in data["campaigns"]}
        campaign_entry = by_slug["genmedia"]
        self.assertEqual(campaign_entry["slug"], "genmedia")
        by_id = {r["id"]: r for r in campaign_entry["registrations"]}
        self.assertEqual(by_id[no_row_reg.pk]["diagnosis"], "no_notification_row")
        self.assertEqual(by_id[failed_reg.pk]["diagnosis"], "notification_failed")
        self.assertEqual(
            by_id[failed_reg.pk]["notifications"][0]["last_error"],
            "HTTPError",
        )

        # active_only=false includes inactive campaign
        resp_all = self.client.get(
            "/api/registration-campaigns/approval-notifications/reconcile/?active_only=false&include_registrations=false",
            **self.staff_headers,
        )
        self.assertEqual(resp_all.status_code, 200)
        all_data = resp_all.json()
        self.assertGreater(all_data["totals"]["campaigns_checked"], data["totals"]["campaigns_checked"])
        self.assertEqual(all_data["totals"]["missing_count"], 3)
        self.assertNotIn("registrations", all_data["campaigns"][0])
