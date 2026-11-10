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
    @patch("scripts.genmedia_evening_batch.approve_batches")
    @patch("scripts.genmedia_evening_batch.select_approvable")
    @patch("scripts.genmedia_evening_batch.fetch_pending")
    @patch("subprocess.run")
    def test_daily_auto_approval_sends_no_sponsor_email(
        self, send_command, fetch_pending, select_approvable, approve_batches
    ):
        row = {
            "id": 1,
            "email": "applicant@example.com",
            "name": "Applicant",
            "country": "Germany",
        }
        fetch_pending.return_value = ([row], 1)
        select_approvable.return_value = ([row], [])
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

        approve_batches.assert_called_once()
        send_command.assert_not_called()

    @patch("scripts.genmedia_full_export.fetch_all")
    @patch("scripts.genmedia_full_export.subprocess.run")
    def test_weekly_report_sends_one_email_with_one_csv(
        self, send_command, fetch_all
    ):
        fetch_all.return_value = [
            {"id": 1, "email": "applicant@example.com", "status": "approved"}
        ]
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
