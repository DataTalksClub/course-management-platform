import logging
from typing import Any

from course_management.datamailer.payloads.registration_confirmations import (
    registration_confirmation_payload,
)
from course_management.datamailer.sync.transactional import (
    notification_config_or_audit,
    send_transactional_email,
)

logger = logging.getLogger(__name__)


def send_registration_confirmation_email(
    registration,
) -> dict[str, Any] | None:
    try:
        return _send_registration_confirmation_email(registration)
    except Exception:
        logger.exception(
            "Relay registration confirmation failed registration_id=%s",
            registration.pk,
        )
        return None


def _send_registration_confirmation_email(registration):
    if (
        notification_config_or_audit(
            "registration-confirmation", registration.pk
        )
        is None
    ):
        return None
    payload = registration_confirmation_payload(registration)
    if payload is None:
        return None
    return send_transactional_email(payload)
