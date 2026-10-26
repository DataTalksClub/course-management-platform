from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from courses.models import CourseRegistration, RegistrationDigestSend
from courses.models.registration_digest import RegistrationDigestSend as DigestModel
from courses.registration_wall import approve_registration
from courses.tests.registration_campaign_base import RegistrationCampaignBase


RELAY_SETTINGS = {
    "RELAY_URL": "https://relay.example.com",
    "RELAY_API_KEY": "test-key",
    "RELAY_CLIENT": "dtc-courses",
    "RELAY_AUDIENCE": "dtc-courses",
}

# 2026-10-26 is CET (UTC+1): 08:30 UTC == 09:30 Berlin (due), and
# 07:30 UTC == 08:30 Berlin (not due).
DUE_NOW = datetime(2026, 10, 26, 8, 30, tzinfo=dt_timezone.utc)
EARLY_NOW = datetime(2026, 10, 26, 7, 30, tzinfo=dt_timezone.utc)


def relay_ok(*args, **kwargs):
    from unittest.mock import Mock
    response = Mock()
    response.json.return_value = {"message": {"id": "msg-1", "status": "queued"}}
    return response


@override_settings(**RELAY_SETTINGS)
class RegistrationDigestTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        self.course.requires_registration_approval = True
        self.course.save()

    def make_registration(self, email, name="Applicant", confirmed=False, age=None, now=None):
        registration = CourseRegistration.objects.create(
            campaign=self.campaign,
            email=email,
            name=name,
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            email_confirmed=confirmed,
        )
        moment = now or timezone.now()
        if age is None:
            age = timedelta(hours=1)
        CourseRegistration.objects.filter(pk=registration.pk).update(
            created_at=moment - age,
        )
        registration.refresh_from_db()
        return registration

    def request_path(self):
        return "course_management.relay.application_notifications.requests.request"

    def test_new_registration_creates_no_operator_notification(self):
        from course_management.relay.application_notifications import (
            process_application_notifications,
        )
        self.make_registration("fresh@example.com", now=DUE_NOW)
        process_application_notifications()
        self.assertFalse(CourseRegistration.objects.get().application_notifications.exists())

    def test_digest_covers_last_24h_grouped_by_course(self):
        from course_management.relay.registration_digest import send_registration_digest
        self.make_registration(
            "jane@example.com", name="Jane Doe", confirmed=True,
            age=timedelta(hours=1), now=DUE_NOW,
        )
        self.make_registration(
            "john@example.com", name="John Smith", confirmed=False,
            age=timedelta(hours=2), now=DUE_NOW,
        )
        other_course = self.course
        other_course.pk = None
        other_course.slug = "other-course"
        other_course.title = "Other Course"
        other_course.save()
        other_campaign = self.campaign
        other_campaign.pk = None
        other_campaign.slug = "other-campaign"
        other_campaign.title = "Other Campaign"
        other_campaign.current_course = other_course
        other_campaign.save()
        other = CourseRegistration.objects.create(
            campaign=other_campaign,
            email="other@example.com",
            name="Other Person",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            email_confirmed=True,
        )
        CourseRegistration.objects.filter(pk=other.pk).update(
            created_at=DUE_NOW - timedelta(hours=3),
        )
        with patch(self.request_path(), side_effect=relay_ok) as request:
            result = send_registration_digest(now=DUE_NOW)
        self.assertTrue(result.sent)
        self.assertEqual(result.total_count, 3)
        self.assertEqual(request.call_count, 1)
        payload = request.call_args.kwargs["json"]
        self.assertEqual(payload["template_key"], "registration-digest-operator")
        self.assertEqual(payload["email"], "alexey@datatalks.club")
        self.assertTrue(
            payload["idempotency_key"].startswith("cmp-registration-digest:2026-10-26:")
        )
        context = payload["context"]
        self.assertEqual(context["digest_date"], "2026-10-26")
        self.assertEqual(context["total_count"], 3)
        self.assertEqual(context["confirmed_count"], 2)
        self.assertEqual(context["unconfirmed_count"], 1)
        self.assertEqual(context["course_count"], 2)
        summary = context["summary"]
        self.assertIn("LLM Zoomcamp 2026", summary)
        self.assertIn("Other Course", summary)
        self.assertIn("Jane Doe <jane@example.com> — confirmed", summary)
        self.assertIn("John Smith <john@example.com> — unconfirmed", summary)
        self.assertIn("status=pending", summary)
        row = RegistrationDigestSend.objects.get(date=DUE_NOW.date())
        self.assertEqual(row.status, DigestModel.Status.SENT)
        self.assertEqual(row.total_count, 3)
        self.assertEqual(row.confirmed_count, 2)
        self.assertEqual(row.unconfirmed_count, 1)
        self.assertEqual(row.course_count, 2)
        self.assertEqual(row.recipients, ["alexey@datatalks.club"])

    def test_digest_window_excludes_older_registrations(self):
        from course_management.relay.registration_digest import send_registration_digest
        self.make_registration(
            "recent@example.com", age=timedelta(hours=23), now=DUE_NOW,
        )
        self.make_registration(
            "edge@example.com", age=timedelta(hours=24), now=DUE_NOW,
        )
        self.make_registration(
            "old@example.com", age=timedelta(hours=25), now=DUE_NOW,
        )
        with patch(self.request_path(), side_effect=relay_ok) as request:
            result = send_registration_digest(now=DUE_NOW)
        self.assertTrue(result.sent)
        self.assertEqual(result.total_count, 2)
        summary = request.call_args.kwargs["json"]["context"]["summary"]
        self.assertIn("recent@example.com", summary)
        self.assertIn("edge@example.com", summary)
        self.assertNotIn("old@example.com", summary)

    def test_digest_zero_registrations_sends_nothing(self):
        from course_management.relay.registration_digest import send_registration_digest
        with patch(self.request_path(), side_effect=relay_ok) as request:
            result = send_registration_digest(now=DUE_NOW)
        self.assertFalse(result.sent)
        self.assertEqual(result.reason, "empty")
        request.assert_not_called()
        row = RegistrationDigestSend.objects.get(date=DUE_NOW.date())
        self.assertEqual(row.status, DigestModel.Status.SKIPPED_EMPTY)
        self.assertEqual(row.total_count, 0)
        with patch(self.request_path(), side_effect=relay_ok) as request:
            repeat = send_registration_digest(now=DUE_NOW)
        self.assertFalse(repeat.sent)
        self.assertEqual(repeat.reason, "already-sent")
        request.assert_not_called()

    def test_digest_is_idempotent_per_day(self):
        from course_management.relay.registration_digest import send_registration_digest
        self.make_registration("once@example.com", now=DUE_NOW)
        with patch(self.request_path(), side_effect=relay_ok) as request:
            first = send_registration_digest(now=DUE_NOW)
            second = send_registration_digest(now=DUE_NOW)
        self.assertTrue(first.sent)
        self.assertFalse(second.sent)
        self.assertEqual(second.reason, "already-sent")
        request.assert_called_once()
        first_key = request.call_args.kwargs["json"]["idempotency_key"]
        with patch(self.request_path(), side_effect=relay_ok) as request:
            forced = send_registration_digest(now=DUE_NOW, force=True)
        self.assertTrue(forced.sent)
        self.assertEqual(
            request.call_args.kwargs["json"]["idempotency_key"], first_key,
        )

    @override_settings(APPLICATION_NOTIFICATION_OPERATORS=[
        "Second@Example.com", "alexey@datatalks.club", "second@example.com",
    ])
    def test_digest_goes_to_each_operator_once(self):
        from course_management.relay.registration_digest import send_registration_digest
        self.make_registration("multi@example.com", now=DUE_NOW)
        with patch(self.request_path(), side_effect=relay_ok) as request:
            result = send_registration_digest(now=DUE_NOW)
        self.assertTrue(result.sent)
        self.assertEqual(request.call_count, 2)
        emails = sorted(
            call.kwargs["json"]["email"] for call in request.call_args_list
        )
        self.assertEqual(emails, ["alexey@datatalks.club", "second@example.com"])
        keys = [
            call.kwargs["json"]["idempotency_key"]
            for call in request.call_args_list
        ]
        self.assertEqual(len(set(keys)), 2)
        self.assertTrue(all(
            key.startswith("cmp-registration-digest:2026-10-26:") for key in keys
        ))

    def test_digest_not_due_before_berlin_0900(self):
        from course_management.relay.registration_digest import (
            digest_due,
            maybe_send_scheduled_digest,
        )
        self.make_registration("early@example.com", now=EARLY_NOW)
        self.assertFalse(digest_due(EARLY_NOW))
        with patch(self.request_path(), side_effect=relay_ok) as request:
            self.assertIsNone(maybe_send_scheduled_digest(now=EARLY_NOW))
        request.assert_not_called()
        self.assertTrue(digest_due(DUE_NOW))

    def test_scheduled_digest_never_raises(self):
        import requests
        from course_management.relay.registration_digest import (
            maybe_send_scheduled_digest,
        )
        self.make_registration("boom@example.com", now=DUE_NOW)
        with patch(self.request_path(), side_effect=requests.Timeout("down")):
            result = maybe_send_scheduled_digest(now=DUE_NOW)
        self.assertFalse(result.sent)
        self.assertEqual(result.reason, "failed")
        self.assertFalse(
            RegistrationDigestSend.objects.filter(date=DUE_NOW.date()).exists(),
        )

    @override_settings(RELAY_TRANSACTIONAL_DRY_RUN=True)
    def test_digest_dry_run_accepts_render_without_message_id(self):
        from course_management.relay.registration_digest import send_registration_digest
        self.make_registration("dry@example.com", now=DUE_NOW)
        with patch(self.request_path()) as request:
            request.return_value.json.return_value = {
                "message": {"id": None, "status": "queued"},
                "would_deliver": True,
            }
            result = send_registration_digest(now=DUE_NOW)
        self.assertTrue(result.sent)
        self.assertTrue(request.call_args.kwargs["json"]["dry_run"])
        row = RegistrationDigestSend.objects.get(date=DUE_NOW.date())
        self.assertEqual(row.status, DigestModel.Status.SENT)
        self.assertEqual(row.relay_message_ids, [""])

    def test_approval_mail_still_queued_after_digest_change(self):
        registration = self.make_registration("decide@example.com", now=DUE_NOW)
        approve_registration(registration)
        self.assertTrue(registration.application_notifications.filter(
            template_key="application-approved",
            recipient="decide@example.com",
        ).exists())
