from unittest.mock import patch

from django.test import override_settings

from courses.models import CourseRegistration
from courses.registration_wall import approve_registration
from courses.tests.registration_campaign_base import RegistrationCampaignBase


@override_settings(
    RELAY_URL="https://relay.example.com",
    RELAY_API_KEY="test-key",
    RELAY_CLIENT="dtc-courses",
    RELAY_AUDIENCE="dtc-courses",
)
class ApplicationNotificationTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        self.course.requires_registration_approval = True
        self.course.save()

    def registration(self):
        return CourseRegistration.objects.create(
            campaign=self.campaign,
            email="applicant@example.com",
            name="Applicant",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
        )

    def test_approval_queues_applicant_email(self):
        registration = self.registration()
        approve_registration(registration)
        from django.apps import apps
        notification_model = apps.get_model("courses", "ApplicationNotification")
        self.assertTrue(notification_model.objects.filter(
            registration=registration,
            template_key="application-approved",
            recipient="applicant@example.com",
        ).exists())

    def notifications(self):
        from courses.models import ApplicationNotification
        return ApplicationNotification.objects.all()

    def test_new_pending_application_notifies_operator_once(self):
        registration = self.registration()
        registration.name = "Updated"
        registration.save()
        self.assertFalse(self.notifications().exists())

    @override_settings(APPLICATION_NOTIFICATION_OPERATORS=[
        "OTHER@example.com", "alexey@datatalks.club", "other@example.com",
    ])
    def test_configured_operator_list_includes_default_and_deduplicates(self):
        from course_management.relay.application_notifications import (
            operator_recipients,
        )
        self.assertEqual(
            operator_recipients(),
            ["alexey@datatalks.club", "other@example.com"],
        )

    def test_open_course_has_no_operator_notification(self):
        self.course.requires_registration_approval = False
        self.course.save()
        self.registration()
        self.assertFalse(self.notifications().exists())

    def test_wall_course_creation_queues_no_operator_notification(self):
        self.registration()
        self.assertFalse(self.notifications().exists())

    def test_rollback_also_rolls_back_notifications(self):
        from django.db import transaction
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.registration()
                raise RuntimeError("rollback")
        self.assertFalse(self.notifications().exists())

    def test_repeated_decision_and_unrelated_save_do_not_duplicate(self):
        registration = self.registration()
        approve_registration(registration)
        approve_registration(registration)
        registration.status = "rejected"
        registration.save(update_fields=["name"])
        self.assertEqual(self.notifications().filter(template_key="application-approved").count(), 1)
        self.assertFalse(self.notifications().filter(template_key="application-rejected").exists())

    def test_reject_and_later_approval_are_separate_decisions(self):
        registration = self.registration()
        approve_registration(registration)
        registration.status = "rejected"
        registration.save(update_fields=["status"])
        registration.save(update_fields=["status"])
        approve_registration(registration)
        self.assertEqual(list(self.notifications().filter(decision_sequence__gt=0).order_by(
            "decision_sequence").values_list("template_key", flat=True)), [
                "application-approved", "application-rejected", "application-approved",
            ])
        self.assertEqual(self.notifications().values("idempotency_key").distinct().count(), 3)

    def test_cadmin_approve_and_reject_queue_applicant_email(self):
        from accounts.models import CustomUser
        from django.urls import reverse
        staff = CustomUser.objects.create_user(
            username="operator", email="operator@example.com", is_staff=True,
        )
        self.client.force_login(staff)
        registration = self.registration()
        url = reverse("cadmin_campaign_registration_decide", kwargs={
            "campaign_slug": self.campaign.slug,
        })
        for action, template in [("approve", "application-approved"), ("reject", "application-rejected")]:
            response = self.client.post(url, {"action": action, "registration_id": registration.pk})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.notifications().filter(template_key=template).count(), 1)

    @patch("course_management.relay.application_notifications.requests.request")
    def test_relay_sends_once_per_notification(self, request):
        from course_management.relay.application_notifications import process_application_notifications
        request.return_value.json.return_value = {"message": {"id": 123, "status": "queued"}}
        registration = self.registration()
        approve_registration(registration)
        process_application_notifications()
        process_application_notifications()
        request.assert_called_once()
        payload = request.call_args.kwargs["json"]
        self.assertEqual(payload["template_key"], "application-approved")
        self.assertEqual(payload["client"], "dtc-courses")
        self.assertEqual(payload["audience"], "dtc-courses")
        self.assertEqual(payload["category_tag"], "transactional")
        self.assertEqual(self.notifications().get().status, "sent")

    @patch("course_management.relay.application_notifications.record_event")
    @patch("course_management.relay.application_notifications.requests.request")
    def test_relay_failure_is_failed_logged_and_alerted_then_retried_with_same_key(self, request, event):
        import requests
        from django.utils import timezone
        from course_management.relay.application_notifications import process_application_notifications
        from data.management.commands.check_cmp_workers import worker_alarms
        registration = self.registration()
        approve_registration(registration)
        request.side_effect = requests.Timeout("private provider response")
        with self.assertLogs("course_management.relay.application_notifications", level="ERROR") as logs:
            process_application_notifications()
        notification = self.notifications().get()
        self.assertEqual(notification.status, "failed")
        self.assertEqual(notification.last_error, "Timeout")
        self.assertNotIn("private provider response", str(logs.output))
        self.assertIn("application_notifications:failed", worker_alarms())
        event.assert_called_once()
        self.assertEqual(event.call_args.args[0], "datamailer.health_warning")
        first_key = request.call_args.kwargs["json"]["idempotency_key"]
        self.notifications().update(next_attempt_at=timezone.now())
        request.side_effect = None
        request.return_value.json.return_value = {"message": {"id": 123, "status": "queued"}}
        process_application_notifications()
        self.assertEqual(request.call_args.kwargs["json"]["idempotency_key"], first_key)
        self.assertEqual(self.notifications().get().status, "sent")

    @override_settings(RELAY_API_KEY="")
    def test_missing_relay_configuration_fails_loudly(self):
        from course_management.relay.application_notifications import process_application_notifications
        registration = self.registration()
        approve_registration(registration)
        with self.assertLogs("course_management.relay.application_notifications", level="ERROR"):
            process_application_notifications()
        self.assertEqual(self.notifications().get().status, "failed")

    @override_settings(RELAY_TRANSACTIONAL_DRY_RUN=True)
    @patch("course_management.relay.application_notifications.requests.request")
    def test_dev_dry_run_accepts_render_without_message_id(self, request):
        from course_management.relay.application_notifications import process_application_notifications
        request.return_value.json.return_value = {
            "message": {"id": None, "status": "queued"}, "would_deliver": True,
        }
        registration = self.registration()
        approve_registration(registration)
        process_application_notifications()
        self.assertTrue(request.call_args.kwargs["json"]["dry_run"])
        self.assertEqual(self.notifications().get().status, "sent")
        self.assertEqual(self.notifications().get().relay_message_id, "")

    @patch("course_management.relay.application_notifications.requests.request")
    def test_unacknowledged_or_suppressed_send_is_failed(self, request):
        from course_management.relay.application_notifications import process_application_notifications
        registration = self.registration()
        approve_registration(registration)
        request.return_value.json.return_value = {"message": {"id": 123, "status": "skipped"}}
        with self.assertLogs("course_management.relay.application_notifications", level="ERROR"):
            process_application_notifications()
        self.assertEqual(self.notifications().get().status, "failed")

    def test_admin_bulk_decisions_send_once_per_selected_applicant(self):
        from django.contrib.admin.sites import AdminSite
        from courses.admin.course import CourseRegistrationAdmin
        first = self.registration()
        second = CourseRegistration.objects.create(
            campaign=self.campaign, email="second@example.com", name="Second",
        )
        model_admin = CourseRegistrationAdmin(CourseRegistration, AdminSite())
        selected = CourseRegistration.objects.filter(pk__in=[first.pk, second.pk])
        model_admin.approve_selected(None, selected)
        model_admin.approve_selected(None, selected)
        model_admin.reject_selected(None, selected)
        model_admin.reject_selected(None, selected)
        for template in ["application-approved", "application-rejected"]:
            self.assertEqual(self.notifications().filter(template_key=template).count(), 2)

    def test_blank_applicant_name_still_supplies_required_template_context(self):
        registration = CourseRegistration.objects.create(
            campaign=self.campaign, email="unnamed@example.com", name="",
        )
        approve_registration(registration)
        self.assertEqual(self.notifications().count(), 1)
        for notification in self.notifications():
            self.assertEqual(notification.context["name"], "Applicant")
