from typing import Any

from ..payloads.registration_confirmations import (
    registration_confirmation_payload,
)
from .transactional import (
    notification_config_or_audit,
    send_transactional_email,
)


def send_registration_confirmation_email(
    registration,
) -> dict[str, Any] | None:
    if notification_config_or_audit(
        "registration-confirmation", registration.pk
    ) is None:
        return None
    payload = registration_confirmation_payload(registration)
    if payload is None:
        return None
    return send_transactional_email(payload)
