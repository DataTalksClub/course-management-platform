from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.template import Context, Template
from django.utils import timezone

from courses.models import CourseRegistration
from courses.tests.registration_campaign_base import RegistrationCampaignBase


class ConfirmationReminderTests(RegistrationCampaignBase):
    def make_registration(self, age, **fields):
        row = CourseRegistration.objects.create(
            campaign=self.campaign, email="reminder@example.com", name="Private Name",
            email_confirmation_token="original", email_confirmation_sent_at=self.now,
            **fields,
        )
        CourseRegistration.objects.filter(pk=row.pk).update(created_at=self.now - age)
        row.refresh_from_db()
        return row

    def setUp(self):
        super().setUp()
        self.now = timezone.now()
        self.sender = patch("course_management.relay.confirmation_reminders.send_transactional_message", return_value="test-message")
        self.send = self.sender.start()
        self.addCleanup(self.sender.stop)

    def run_job(self, **kwargs):
        from course_management.relay.confirmation_reminders import process_confirmation_reminders
        return process_confirmation_reminders(now=self.now, **kwargs)

    def test_24h_and_72h_boundaries_and_no_third_reminder(self):
        row = self.make_registration(timedelta(hours=24) - timedelta(microseconds=1))
        self.run_job()
        self.send.assert_not_called()
        self.now += timedelta(microseconds=1)
        self.assertEqual(self.run_job()["reminded"], 1)
        first_key = self.send.call_args.args[3]
        self.run_job()
        self.assertEqual(self.send.call_count, 1)
        self.now += timedelta(hours=48) - timedelta(microseconds=1)
        self.run_job()
        self.assertEqual(self.send.call_count, 1)
        self.now += timedelta(microseconds=1)
        self.run_job()
        self.assertEqual(self.send.call_count, 2)
        self.assertNotEqual(first_key, self.send.call_args.args[3])
        for _ in range(3):
            self.run_job()
        self.assertEqual(self.send.call_count, 2)
        row.refresh_from_db()
        self.assertIsNotNone(row.confirmation_reminder_1_sent_at)
        self.assertIsNotNone(row.confirmation_reminder_2_sent_at)

    def test_final_copy_has_berlin_deadline_and_confirm_link(self):
        from course_management.relay.application_templates import APPLICATION_TEMPLATES
        from zoneinfo import ZoneInfo
        row = self.make_registration(timedelta(hours=72), confirmation_reminder_1_sent_at=self.now-timedelta(hours=48))
        self.run_job()
        key, recipient, context, _ = self.send.call_args.args
        draft = APPLICATION_TEMPLATES[key]
        body = Template(draft["text_body"]).render(Context(context))
        self.assertIn("last reminder", body)
        self.assertIn((row.created_at+timedelta(days=7)).astimezone(ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d"), body)
        self.assertIn("Europe/Berlin", body)
        self.assertIn("your registration will be deleted", body)
        self.assertIn("/register/confirm/original/", body)
        self.assertEqual(recipient, row.email_normalized)

    def test_delete_only_after_deadline_with_final_and_never_confirmed(self):
        row = self.make_registration(timedelta(days=7), confirmation_reminder_2_sent_at=self.now)
        self.assertEqual(self.run_job()["deleted"], 0)
        self.now += timedelta(microseconds=1)
        self.assertEqual(self.run_job()["deleted"], 1)
        self.assertFalse(CourseRegistration.objects.filter(pk=row.pk).exists())
        confirmed = self.make_registration(timedelta(days=8), email_confirmed=True, confirmation_reminder_2_sent_at=self.now)
        self.run_job()
        self.assertTrue(CourseRegistration.objects.filter(pk=confirmed.pk).exists())
        self.send.assert_not_called()

    def test_overdue_without_final_is_not_deleted(self):
        row = self.make_registration(timedelta(days=8))
        self.assertEqual(self.run_job()["deleted"], 0)
        self.assertTrue(CourseRegistration.objects.filter(pk=row.pk).exists())

    def test_confirmed_between_reminders_gets_nothing(self):
        row = self.make_registration(timedelta(hours=24))
        self.run_job()
        row.email_confirmed = True
        row.save(update_fields=["email_confirmed"])
        self.now += timedelta(days=10)
        self.run_job()
        self.assertEqual(self.send.call_count, 1)
        self.assertTrue(CourseRegistration.objects.filter(pk=row.pk).exists())

    def test_dry_run_no_writes_or_pii(self):
        row = self.make_registration(timedelta(hours=24))
        output = StringIO()
        call_command("process_confirmation_reminders", "--dry-run", stdout=output)
        self.send.assert_not_called()
        row.refresh_from_db()
        self.assertIsNone(row.confirmation_reminder_1_sent_at)
        self.assertNotIn("@", output.getvalue())
        self.assertNotIn(row.name, output.getvalue())

    def test_refresh_short_lived_token_without_changing_resend_counter(self):
        row = self.make_registration(timedelta(hours=24), email_confirmation_resend_count=10)
        CourseRegistration.objects.filter(pk=row.pk).update(email_confirmation_sent_at=row.created_at-timedelta(days=1))
        self.run_job()
        row.refresh_from_db()
        self.assertNotEqual(row.email_confirmation_token, "original")
        self.assertEqual(row.email_confirmation_resend_count, 10)
        self.assertEqual(row.email_confirmation_sent_at, self.now)

    def test_send_failure_retries_same_token_and_idempotency_key(self):
        row = self.make_registration(timedelta(hours=24))
        CourseRegistration.objects.filter(pk=row.pk).update(email_confirmation_sent_at=None)
        self.send.side_effect = TimeoutError
        self.assertEqual(self.run_job()["failed"], 1)
        first_call = self.send.call_args
        row.refresh_from_db()
        self.assertIsNone(row.confirmation_reminder_1_sent_at)
        self.send.side_effect = None
        self.run_job()
        self.assertEqual(self.send.call_args, first_call)

    def test_worker_lock_contention_sends_nothing(self):
        from contextlib import contextmanager
        @contextmanager
        def locked(*args):
            yield False
        self.make_registration(timedelta(hours=24))
        with patch("course_management.relay.confirmation_reminders.worker_lock", locked):
            self.run_job()
        self.send.assert_not_called()

    def test_expired_token_is_refreshed_and_valid_token_is_preserved(self):
        row = self.make_registration(timedelta(days=8), confirmation_reminder_1_sent_at=self.now)
        CourseRegistration.objects.filter(pk=row.pk).update(email_confirmation_sent_at=self.now-timedelta(days=7))
        self.run_job()
        row.refresh_from_db()
        self.assertNotEqual(row.email_confirmation_token, "original")
        self.assertIn(row.email_confirmation_token, self.send.call_args.args[2]["confirmation_url"])

    def test_dry_run_does_not_delete_eligible_registration(self):
        row = self.make_registration(timedelta(days=8), confirmation_reminder_2_sent_at=self.now)
        self.assertEqual(self.run_job(dry_run=True)["deleted"], 1)
        self.assertTrue(CourseRegistration.objects.filter(pk=row.pk).exists())
        self.send.assert_not_called()

    def test_minutely_outbox_invokes_reminders(self):
        from django.core.management.base import CommandError
        with patch("data.management.commands.process_datamailer_outbox.process_application_notifications"), patch("data.management.commands.process_datamailer_outbox.maybe_send_scheduled_digest"), patch("course_management.relay.confirmation_reminders.process_confirmation_reminders") as reminders, patch("data.management.commands.process_datamailer_outbox.DatamailerConfig.from_settings", return_value=None):
            with self.assertRaises(CommandError):
                call_command("process_datamailer_outbox", limit=5)
        reminders.assert_called_once_with(limit=5)
