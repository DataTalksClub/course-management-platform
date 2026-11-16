from datetime import timedelta
from unittest.mock import Mock, patch

import requests
from django.utils import timezone

from data.models import DatamailerOutboxEvent, DatamailerOutboxStatus
from course_management.datamailer_outbox_dispatch import (
    dispatch_datamailer_outbox_event,
)
from course_management.datamailer_outbox_retry import (
    RATE_LIMIT_RETRY_FLOOR_SECONDS,
    retry_delay,
    status_for_error,
)
from course_management.datamailer_outbox_runs import (
    process_due_datamailer_outbox,
)
from courses.tests.datamailer_outbox_base import (
    RELAY_SETTINGS,
    DatamailerOutboxTestBase,
)


class DatamailerOutboxRetryStatusTest(DatamailerOutboxTestBase):
    def test_outbox_status_for_error_classifies_retryable_errors(self):
        rate_limit_error = self.http_error(429)
        rate_limit_attempt = self.outbox_attempt()
        rate_limit_status = status_for_error(
            rate_limit_error,
            rate_limit_attempt,
        )
        self.assertEqual(rate_limit_status, DatamailerOutboxStatus.RETRYING)

        unavailable_error = self.http_error(503)
        unavailable_attempt = self.outbox_attempt()
        unavailable_status = status_for_error(
            unavailable_error,
            unavailable_attempt,
        )
        self.assertEqual(unavailable_status, DatamailerOutboxStatus.RETRYING)

    def test_outbox_status_for_error_classifies_cloudfront_403_as_retrying(self):
        cf_response = Mock(
            status_code=403,
            headers={"Server": "CloudFront", "Content-Type": "text/html"},
            text="<html><body><h1>403 ERROR</h1><p>The request could not be satisfied.</p></body></html>",
        )
        cf_error = requests.HTTPError("403 Client Error: Forbidden", response=cf_response)
        self.assertEqual(
            status_for_error(cf_error, self.outbox_attempt()),
            DatamailerOutboxStatus.RETRYING,
        )

        relay_403_response = Mock(
            status_code=403,
            headers={"Content-Type": "application/json"},
            text='{"error": "forbidden"}',
        )
        relay_403_error = requests.HTTPError("403 Client Error: Forbidden", response=relay_403_response)
        self.assertEqual(
            status_for_error(relay_403_error, self.outbox_attempt()),
            DatamailerOutboxStatus.FAILED,
        )

    def test_outbox_status_for_error_classifies_failed_errors(self):
        network_error = requests.RequestException("network error")
        final_attempt = self.outbox_attempt(attempt_count=3, max_attempts=3)

        bad_request_error = self.http_error(400)
        bad_request_attempt = self.outbox_attempt()
        bad_request_status = status_for_error(
            bad_request_error,
            bad_request_attempt,
        )
        self.assertEqual(bad_request_status, DatamailerOutboxStatus.FAILED)

        final_status = status_for_error(network_error, final_attempt)
        self.assertEqual(final_status, DatamailerOutboxStatus.FAILED)


class DatamailerOutboxRetryDelayTest(DatamailerOutboxTestBase):
    def test_retry_delay_doubles_up_to_fifteen_minute_cap(self):
        with patch(
            "course_management.datamailer_outbox_retry.random.uniform",
            return_value=0.0,
        ):
            self.assertEqual(retry_delay(1), timedelta(seconds=1))
            self.assertEqual(retry_delay(4), timedelta(seconds=8))
            self.assertEqual(retry_delay(12), timedelta(seconds=900))
            self.assertEqual(retry_delay(40), timedelta(seconds=900))

    def test_retry_delay_adds_jitter(self):
        with patch(
            "course_management.datamailer_outbox_retry.random.uniform",
            return_value=100.0,
        ):
            self.assertEqual(retry_delay(12), timedelta(seconds=1000))

    def test_outbox_events_default_to_twenty_four_attempts(self):
        event = DatamailerOutboxEvent.objects.create(
            event_id="cmp-datamailer-event:test-retry-default",
            event_type="contact.update_preferences",
            idempotency_key="test:retry-default",
        )

        self.assertEqual(event.max_attempts, 24)

    def test_rate_limit_retry_delay_uses_floor(self):
        cf_response = Mock(
            status_code=403,
            headers={"Server": "CloudFront", "Content-Type": "text/html"},
            text="The request could not be satisfied.",
        )
        cf_error = requests.HTTPError("403 Client Error: Forbidden", response=cf_response)
        with patch(
            "course_management.datamailer_outbox_retry.random.uniform",
            return_value=0.0,
        ):
            self.assertEqual(
                retry_delay(1, exc=cf_error),
                timedelta(seconds=RATE_LIMIT_RETRY_FLOOR_SECONDS),
            )

    def test_process_due_outbox_pauses_on_waf_403_and_respects_time_budget(self):
        now = timezone.now()
        first = DatamailerOutboxEvent.objects.create(
            event_id="cmp-datamailer-event:waf-1",
            event_type="contact.erase",
            idempotency_key="waf-1",
            payload={"email": "a@example.com"},
            next_attempt_at=now,
        )
        second = DatamailerOutboxEvent.objects.create(
            event_id="cmp-datamailer-event:waf-2",
            event_type="contact.erase",
            idempotency_key="waf-2",
            payload={"email": "b@example.com"},
            next_attempt_at=now,
        )
        cf_response = Mock(
            status_code=403,
            headers={"Server": "CloudFront", "Content-Type": "text/html"},
            text="The request could not be satisfied.",
        )
        cf_error = requests.HTTPError("403 Client Error: Forbidden", response=cf_response)
        with self.settings(**RELAY_SETTINGS), patch(
            "course_management.datamailer_outbox_dispatch.send_event",
            side_effect=cf_error,
        ) as send_mock:
            counts = process_due_datamailer_outbox(record_run=False)

        self.assertEqual(send_mock.call_count, 1)
        self.assertEqual(counts["processed"], 1)
        self.assertEqual(counts["retrying"], 1)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, DatamailerOutboxStatus.RETRYING)
        self.assertEqual(second.status, DatamailerOutboxStatus.PENDING)

    def test_permanent_outbox_failure_logs_and_records_failed_event(self):
        event = DatamailerOutboxEvent.objects.create(
            event_id="cmp-datamailer-event:perm-fail",
            event_type="contact.erase",
            idempotency_key="perm-fail",
            payload={"email": "c@example.com"},
            next_attempt_at=timezone.now(),
        )
        bad_response = Mock(
            status_code=400,
            headers={"Content-Type": "application/json"},
            text='{"error": "bad request"}',
        )
        bad_error = requests.HTTPError("400 Client Error", response=bad_response)
        with self.settings(**RELAY_SETTINGS), patch(
            "course_management.datamailer_outbox_dispatch.send_event",
            side_effect=bad_error,
        ), patch(
            "course_management.datamailer_outbox_dispatch.record_event"
        ) as record_mock, self.assertLogs(
            "course_management.datamailer_outbox_dispatch", level="ERROR"
        ):
            dispatch_datamailer_outbox_event(event)

        event.refresh_from_db()
        self.assertEqual(event.status, DatamailerOutboxStatus.FAILED)
        recorded_names = [call.args[0] for call in record_mock.call_args_list]
        self.assertIn("datamailer.outbox_failed", recorded_names)
