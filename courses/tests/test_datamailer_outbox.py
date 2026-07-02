import requests

from data.models import DatamailerOutboxStatus
from course_management.datamailer_outbox_retry import status_for_error
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
