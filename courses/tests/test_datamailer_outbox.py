from datetime import timedelta
from unittest.mock import patch

import requests

from data.models import DatamailerOutboxEvent, DatamailerOutboxStatus
from course_management.datamailer_outbox_retry import (
    retry_delay,
    status_for_error,
)
from courses.tests.datamailer_outbox_base import DatamailerOutboxTestBase


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
