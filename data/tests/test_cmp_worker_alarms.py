"""Worker alarm boundaries and recovery; no transport or production writes."""

import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from data.management.commands.check_cmp_workers import LIMITS, worker_alarms
from data.models import CmpJobState, DatamailerOutboxEvent


class CmpWorkerAlarmTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        for job in LIMITS:
            CmpJobState.objects.update_or_create(
                job=job,
                defaults={
                    "last_success_at": self.now,
                    "last_failed_at": None,
                },
            )

    def command_result(self, alarms):
        output = StringIO()
        with patch(
            "data.management.commands.check_cmp_workers.timezone.now",
            return_value=self.now,
        ):
            if alarms:
                with self.assertRaisesMessage(CommandError, "CMP worker alarm"):
                    call_command("check_cmp_workers", stdout=output)
            else:
                call_command("check_cmp_workers", stdout=output)
        self.assertEqual(json.loads(output.getvalue()), {
            "status": "warning" if alarms else "ok", "alarms": alarms,
        })

    def test_each_stalled_job_alarms_then_recovers_after_real_success(self):
        for job, limit in LIMITS.items():
            with self.subTest(job=job):
                state = CmpJobState.objects.get(job=job)
                state.last_success_at = self.now - timedelta(seconds=limit)
                state.save()
                self.assertEqual(worker_alarms(self.now), [])
                state.last_success_at -= timedelta(microseconds=1)
                state.save()
                self.command_result([f"{job}:success_stale"])
                state.last_success_at = self.now
                state.save()
                self.command_result([])

    def test_failed_attempt_is_distinct_from_stall_and_clears_on_success(self):
        for job in LIMITS:
            with self.subTest(job=job):
                CmpJobState.objects.filter(job=job).update(
                    last_success_at=self.now - timedelta(seconds=1),
                    last_failed_at=self.now,
                )
                self.command_result([f"{job}:failed"])
                CmpJobState.objects.filter(job=job).update(
                    last_success_at=self.now + timedelta(seconds=1),
                )
                self.command_result([])

    def test_missing_or_never_successful_job_is_stale(self):
        for job in LIMITS:
            with self.subTest(job=job):
                CmpJobState.objects.filter(job=job).delete()
                self.command_result([f"{job}:success_stale"])
                state = CmpJobState.objects.create(job=job)
                self.command_result([f"{job}:success_stale"])
                state.last_success_at = self.now
                state.save()
        self.command_result([])

    def test_backlog_can_alarm_with_fresh_worker_and_clear_when_drained(self):
        for status, age_field, limit in (
            ("pending", "next_attempt_at", 300),
            ("retrying", "next_attempt_at", 300),
            ("processing", "last_attempt_at", 540),
        ):
            with self.subTest(status=status):
                event = DatamailerOutboxEvent.objects.create(
                    event_id=status, event_type="test", idempotency_key=status,
                    status=status,
                    **{age_field: self.now - timedelta(seconds=limit)},
                )
                self.command_result([])
                setattr(event, age_field, self.now - timedelta(seconds=limit + 1))
                event.save()
                self.command_result(["outbox:backlog_age"])
                event.status = "acked"
                event.save()
                self.command_result([])

    def test_successful_job_records_recovery_without_clearing_failure_history(self):
        CmpJobState.objects.filter(job="health").update(
            last_failed_at=self.now - timedelta(seconds=1),
            last_success_at=self.now - timedelta(minutes=20),
        )
        self.command_result(["health:success_stale", "health:failed"])
        # Exercise the scheduled entry point; stub only its business command.
        with patch("data.management.commands.run_cmp_job.call_command"):
            call_command("run_cmp_job", "health", stdout=StringIO())
        state = CmpJobState.objects.get(job="health")
        self.assertEqual(state.last_failed_at, self.now - timedelta(seconds=1))
        self.assertGreater(state.last_success_at, state.last_failed_at)
        self.command_result([])
