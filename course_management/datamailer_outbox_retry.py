from datetime import timedelta

import requests

from data.models import DatamailerOutboxStatus


def http_error_status_code(exc):
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", 0)
    if status_code:
        return status_code
    return 0


def is_non_retryable_http_error(exc):
    if not isinstance(exc, requests.HTTPError):
        return False

    status_code = http_error_status_code(exc)
    if not status_code:
        return False
    is_server_error = status_code >= 500
    is_rate_limited = status_code == 429
    return not is_server_error and not is_rate_limited


def status_for_error(exc, event):
    if event.attempt_count >= event.max_attempts:
        return DatamailerOutboxStatus.FAILED
    if is_non_retryable_http_error(exc):
        return DatamailerOutboxStatus.FAILED
    return DatamailerOutboxStatus.RETRYING


def retry_delay(attempt_count):
    delay_seconds = min(300, 2 ** max(attempt_count - 1, 0))
    return timedelta(seconds=delay_seconds)
