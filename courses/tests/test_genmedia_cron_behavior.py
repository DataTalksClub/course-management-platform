"""Regression tests for the Hetzner Genmedia cron jobs.

All mail and API boundaries are mocked: these tests never send a message.
"""

import os
import subprocess
from datetime import datetime
from unittest.mock import mock_open, patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from scripts.genmedia_evening_batch import run as run_daily_batch
from scripts.genmedia_alerts import report_failure
from scripts.genmedia_full_export import (
    ExportError,
    main as main_full_export,
    run as run_full_export,
)

WEEKLY_RUN_AT = datetime(
    2026, 11, 16, 20, 15, tzinfo=ZoneInfo("Europe/Berlin")
)


class GenmediaCronBehaviorTestCase(SimpleTestCase):
    def setUp(self):
        # Server-side consent count; matches the rows each test returns.
        patcher = patch(
            "scripts.genmedia_full_export.fetch_count", return_value=0
        )
        self.fetch_count = patcher.start()
        self.addCleanup(patcher.stop)

    @patch("scripts.genmedia_evening_batch.approve_batches")
    @patch("scripts.genmedia_evening_batch.reject_batches")
    @patch("scripts.genmedia_evening_batch.select_decisions")
    @patch("scripts.genmedia_evening_batch.fetch_pending")
    @patch("subprocess.run")
    def test_daily_auto_approval_sends_no_sponsor_email(
        self,
        send_command,
        fetch_pending,
        select_decisions,
        reject_batches,
        approve_batches,
    ):
        row = {
            "id": 1,
            "email": "applicant@example.com",
            "name": "Applicant",
            "country": "Germany",
        }
        fetch_pending.return_value = ([row], 1)
        select_decisions.return_value = ([row], [], [])
        reject_batches.return_value = []
        approve_batches.return_value = [row]

        with patch.dict(
            os.environ,
            {
                "CMP_BASE_URL": "https://cmp.example",
                "CMP_API_TOKEN": "test",
                "DATAMAILER_API_KEY": "test-key",
            },
        ):
            run_daily_batch()

        reject_batches.assert_called_once()
        approve_batches.assert_called_once()
        send_command.assert_not_called()

    @patch("scripts.genmedia_full_export.fetch_all")
    @patch("scripts.genmedia_full_export.subprocess.run")
    def test_weekly_report_sends_one_email_with_one_csv(
        self, send_command, fetch_all
    ):
        fetch_all.return_value = [
            {
                "id": 1,
                "email": "applicant@example.com",
                "status": "approved",
                "accepted_nebius_sharing": True,
            }
        ]
        self.fetch_count.return_value = 1
        send_command.return_value.stdout = "accepted"

        with patch.dict(
            os.environ,
            {
                "CMP_BASE_URL": "https://cmp.example",
                "CMP_API_TOKEN": "test",
                "DATAMAILER_API_KEY": "test-key",
                "GENMEDIA_WEEKLY_REPORT_TO": "mnrozhkov@nebius.com",
            },
        ), patch("os.makedirs"), patch("builtins.open", mock_open()), patch(
            "os.path.getsize", return_value=128
        ):
            run_full_export(now=WEEKLY_RUN_AT)

        self.assertEqual(send_command.call_count, 1)
        command = send_command.call_args.args[0]
        self.assertEqual(command.count("--to"), 1)
        self.assertIn("mnrozhkov@nebius.com", command)
        self.assertEqual(command.count("--attach"), 1)

    @patch("scripts.genmedia_full_export.fetch_all")
    @patch("scripts.genmedia_full_export.subprocess.run")
    def test_weekly_send_has_a_timeout(self, send_command, fetch_all):
        fetch_all.return_value = []
        send_command.return_value.stdout = "accepted"

        with patch.dict(
            os.environ,
            {
                "CMP_BASE_URL": "https://cmp.example",
                "CMP_API_TOKEN": "test",
                "DATAMAILER_API_KEY": "test-key",
                "GENMEDIA_WEEKLY_REPORT_TO": "mnrozhkov@nebius.com",
            },
        ), patch("os.makedirs"), patch("builtins.open", mock_open()), patch(
            "os.path.getsize", return_value=128
        ):
            run_full_export(now=WEEKLY_RUN_AT)

        self.assertEqual(send_command.call_args.kwargs.get("timeout"), 60)

    @patch("scripts.genmedia_full_export.fetch_all", return_value=[])
    @patch("scripts.genmedia_full_export.subprocess.run")
    def test_dry_run_never_sends_email(self, send_command, _fetch_all):
        with patch.dict(
            os.environ,
            {
                "CMP_BASE_URL": "https://cmp.example",
                "CMP_API_TOKEN": "test",
                "GENMEDIA_WEEKLY_REPORT_TO": "mnrozhkov@nebius.com",
            },
        ), patch("os.makedirs"), patch("builtins.open", mock_open()), patch(
            "os.path.getsize", return_value=128
        ):
            result = main_full_export(
                ["--dry-run"], now=datetime(2026, 11, 10, 20, 15, tzinfo=ZoneInfo("Europe/Berlin"))
            )

        self.assertEqual(result, 0)
        send_command.assert_not_called()

    def test_report_cannot_send_before_first_monday_or_on_another_weekday(self):
        with self.assertRaisesRegex(ExportError, "starts on 2026-11-16"):
            run_full_export(now=datetime(2026, 11, 9, 20, 15, tzinfo=ZoneInfo("Europe/Berlin")))
        with self.assertRaisesRegex(ExportError, "only be sent on Monday"):
            run_full_export(now=datetime(2026, 11, 17, 20, 15, tzinfo=ZoneInfo("Europe/Berlin")))

    def test_cron_keeps_daily_approval_and_schedules_monday_evening_report(self):
        with open("deploy/hetzner/genmedia-crontab", encoding="utf-8") as handle:
            cron = handle.read()

        self.assertIn("CRON_TZ=Europe/Berlin", cron)
        self.assertIn("5 20 * * *", cron)
        self.assertIn("15 20 * * 1", cron)
        self.assertIn("GENMEDIA_WEEKLY_REPORT_TO=mnrozhkov@nebius.com", cron)
        # The partner report is on hold (Alexey, 2026-11-23): its line must
        # stay commented out so reinstalling this file cannot send.
        report_lines = [
            line for line in cron.splitlines() if "genmedia_full_export" in line
        ]
        self.assertEqual(len(report_lines), 1)
        self.assertTrue(report_lines[0].startswith("# HOLD"))

    @patch("scripts.genmedia_full_export.report_failure")
    @patch("scripts.genmedia_full_export.fetch_all", return_value=[])
    @patch(
        "scripts.genmedia_full_export.subprocess.run",
        side_effect=subprocess.TimeoutExpired("relay send", 60),
    )
    def test_send_timeout_returns_error_and_alerts(
        self, send_command, _fetch_all, alert
    ):
        with patch.dict(
            os.environ,
            {
                "CMP_BASE_URL": "https://cmp.example",
                "CMP_API_TOKEN": "test",
                "DATAMAILER_API_KEY": "test-key",
                "GENMEDIA_WEEKLY_REPORT_TO": "mnrozhkov@nebius.com",
            },
        ), patch("os.makedirs"), patch("builtins.open", mock_open()), patch(
            "os.path.getsize", return_value=128
        ):
            result = main_full_export([], now=WEEKLY_RUN_AT)

        self.assertEqual(result, 1)
        send_command.assert_called_once()
        alert.assert_called_once()
        self.assertIn("timed out", str(alert.call_args.args[1]))

    @patch("scripts.genmedia_alerts.subprocess.run")
    def test_failure_alert_writes_syslog_and_uses_internal_alert_hook(
        self, run_command
    ):
        with patch.dict(
            os.environ, {"PRINCIPAL_ALERT_TO": "mnrozhkov@nebius.com"}
        ), patch(
            "scripts.genmedia_alerts.DEFAULT_ALERT_COMMAND",
            "/fake/principal-alert.sh",
        ):
            report_failure("Genmedia weekly report", ExportError("send timed out"))

        self.assertEqual(run_command.call_count, 2)
        self.assertEqual(run_command.call_args_list[0].args[0][0], "/usr/bin/logger")
        self.assertEqual(
            run_command.call_args_list[1].args[0], ["/fake/principal-alert.sh"]
        )
        self.assertIn(
            "Genmedia weekly report failed: send timed out",
            run_command.call_args_list[1].kwargs["env"]["PING_ALERT_MESSAGE"],
        )
        self.assertEqual(
            run_command.call_args_list[1].kwargs["env"]["PRINCIPAL_ALERT_TO"],
            "dev@dtcdev.click",
        )


from api.tests.registration_campaign_base import RegistrationCampaignAPITestBase
from courses.decision_messages import REJECTION_MESSAGE_LOCATION
from courses.genmedia_policy import CAMPAIGN_SLUG
from courses.models import (
    ApplicationNotification,
    CourseRegistration,
    RegistrationCampaign,
)


class GenmediaEveningBatchIntegrationTestCase(RegistrationCampaignAPITestBase):
    def _route_requests_to_django_client(self, method, url, headers=None, json=None, timeout=None):
        path = url.removeprefix("https://cmp.example")
        auth = headers.get("Authorization", "") if headers else ""
        if method == "GET":
            django_resp = self.client.get(path, HTTP_AUTHORIZATION=auth)
        else:
            django_resp = self.client.post(
                path,
                data=__import__("json").dumps(json),
                content_type="application/json",
                HTTP_AUTHORIZATION=auth,
            )

        class _Response:
            status_code = django_resp.status_code
            text = django_resp.content.decode("utf-8")

            def json(self_inner):
                return django_resp.json()

        return _Response()

    def test_evening_batch_rejects_restricted_and_approves_eligible_idempotently(self):
        campaign = RegistrationCampaign.objects.get(slug=CAMPAIGN_SLUG)
        eligible = CourseRegistration.objects.create(
            campaign=campaign,
            course=campaign.current_course,
            email="eligible@example.com",
            name="Eligible Applicant",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
        )
        restricted = CourseRegistration.objects.create(
            campaign=campaign,
            course=campaign.current_course,
            email="restricted@example.com",
            name="Restricted Applicant",
            country="Russia",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
        )
        occupied = CourseRegistration.objects.create(
            campaign=campaign,
            course=campaign.current_course,
            email="crimea@example.com",
            name="Crimea Applicant",
            country="Ukraine",
            ukraine_region="crimea",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
        )

        env = {
            "CMP_BASE_URL": "https://cmp.example",
            "CMP_API_TOKEN": self.token.key,
            "CAMPAIGN_SLUG": CAMPAIGN_SLUG,
        }
        with patch.dict(os.environ, env), patch(
            "scripts.genmedia_evening_batch.requests.request",
            side_effect=self._route_requests_to_django_client,
        ):
            run_daily_batch(dry_run=True)
            for reg in (eligible, restricted, occupied):
                reg.refresh_from_db()
                self.assertEqual(reg.status, CourseRegistration.Status.PENDING)
            self.assertEqual(ApplicationNotification.objects.count(), 0)

            run_daily_batch(dry_run=False)
            eligible.refresh_from_db()
            restricted.refresh_from_db()
            occupied.refresh_from_db()
            self.assertEqual(eligible.status, CourseRegistration.Status.APPROVED)
            self.assertEqual(restricted.status, CourseRegistration.Status.REJECTED)
            self.assertEqual(occupied.status, CourseRegistration.Status.REJECTED)

            approved_notif = ApplicationNotification.objects.get(
                registration=eligible, template_key="application-approved"
            )
            self.assertEqual(approved_notif.recipient, "eligible@example.com")

            for reg in (restricted, occupied):
                rejected_notif = ApplicationNotification.objects.get(
                    registration=reg, template_key="application-rejected"
                )
                self.assertEqual(
                    rejected_notif.context["custom_message"],
                    REJECTION_MESSAGE_LOCATION,
                )
            self.assertEqual(ApplicationNotification.objects.count(), 3)

            # Re-running is idempotent: no double rejects, approvals, or emails.
            run_daily_batch(dry_run=False)
            self.assertEqual(ApplicationNotification.objects.count(), 3)
